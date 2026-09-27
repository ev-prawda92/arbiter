#!/usr/bin/env python3
"""Build the read-only hosted demo database, offline.

Ingests the committed Sep 24 2026 venue captures (public Kalshi and Polymarket
markets) through app.venue_intake.discover/sync, then records one example
governed decision on the Xi-succession pattern (KXXISUCCESSOR) through the
normal decision path, and verifies the audit chain. No network is used.

    python3 scripts/seed_demo.py [--db backend/data/demo.db] [--force]
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
FIXTURES = os.path.join(ROOT, "tests", "fixtures")
DEMO_RATIONALE = "Example ruling recorded for this demo; not a venue decision."
XI_SERIES = "KXXISUCCESSOR"


def load_pool() -> dict[str, list[tuple[dict, str]]]:
    pool: dict[str, list[tuple[dict, str]]] = {"kalshi": [], "polymarket": []}
    seen: set[str] = set()
    with gzip.open(os.path.join(FIXTURES, "venue_scan_2026-09-24.json.gz"), "rt") as fh:
        for m in json.load(fh)["markets"]:
            pool[m["venue"]].append((m["raw"], m["url"]))
            if m["venue"] == "kalshi":
                seen.add(str(m["raw"].get("ticker")))
    with gzip.open(os.path.join(FIXTURES, "kalshi_triage_2026-09-24.json.gz"), "rt") as fh:
        for m in json.load(fh)["markets"]:
            if m["market_id"] in seen:
                continue
            raw = {
                "ticker": m["market_id"],
                "event_ticker": m["event_id"],
                "title": m["title"],
                "rules_primary": m["rules"],
                "rules_secondary": "",
                "status": "active",
                "result": "",
                "close_time": "2045-01-01T00:00:00Z",
            }
            pool["kalshi"].append((raw, f"https://kalshi.com/markets/{m['market_id']}"))
    return pool


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", default=os.path.join(ROOT, "backend", "data", "demo.db"))
    ap.add_argument("--force", action="store_true", help="replace an existing demo database")
    args = ap.parse_args(argv)
    db = os.path.abspath(args.db)
    if os.path.exists(db):
        if not args.force:
            print(f"demo database already exists: {db} (use --force to rebuild)")
            return 0
        for suffix in ("", "-wal", "-shm"):
            if os.path.exists(db + suffix):
                os.remove(db + suffix)
    os.makedirs(os.path.dirname(db), exist_ok=True)

    # Configure before importing the app: the store binds to this path at import.
    os.environ["ARBITER_DATABASE_PATH"] = db
    os.environ.pop("ARBITER_DEMO_MODE", None)  # seeding itself must be able to write
    sys.path.insert(0, os.path.join(ROOT, "backend"))
    from fastapi.testclient import TestClient

    from app import venue_intake as vi
    from app.server import app, resolution_store as store

    pool = load_pool()
    ev, fetcher, stats = vi.discover(lambda v, limit: pool.get(v, []), limit=5000, store=store)
    rep = vi.sync(store, ev, fetcher=fetcher, boilerplate=stats["boilerplate"])

    client = TestClient(app)
    queue = client.get("/api/work-queue").json()
    subject = {str(i["id"]): str(i.get("subject") or "") for i in queue.get("items") or []}
    clusters = client.get("/api/overview").json()["agent_brief"]["operations_intelligence"]["clusters"]
    xi = next(
        (c for c in clusters if any(XI_SERIES in subject.get(str(x), "") for x in c.get("case_ids") or [])),
        None,
    )
    if not xi:
        print("FAIL: no Xi-succession work pattern after ingest")
        return 1
    r = client.post(
        "/api/decisions",
        json={
            "cluster_id": xi["cluster_id"],
            "selection": (
                "Only a permanent General Secretary named by the Central Committee counts; "
                "interim or acting leaders do not"
            ),
            "rationale": DEMO_RATIONALE,
            "governing_rule": "Official party announcement of a permanent leader controls",
            "actor": "operator:demo-seed",
        },
    )
    if r.status_code != 200:
        print(f"FAIL: example decision not recorded ({r.status_code}: {r.text[:200]})")
        return 1

    chain = store.verify_audit_chain()
    if not chain.get("ok"):
        print(f"FAIL: audit chain does not verify: {chain}")
        return 1
    print(
        f"demo database: {db}\n"
        f"  work items opened from the captured markets: {rep['totals'].get('work_items_opened')}\n"
        f"  example decision: {r.json()['decision']['decision_id']} on {xi['cluster_id']}\n"
        f"  audit chain: ok ({chain.get('events')} events)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
