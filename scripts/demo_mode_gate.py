#!/usr/bin/env python3
"""Gate for the read-only hosted demo (ARBITER_DEMO_MODE=1).

Properties asserted (fail-closed), on a demo database seeded offline from the
committed Sep 24 2026 venue captures:

  D1  the seed builds offline and the audit chain verifies
  D2  health reports demo_mode
  D3  representative console reads return 200 (overview, work queue,
      precedents, audit overview, lineage of a Xi-succession contract)
  D4  read-only query POSTs the console needs (ask, consistency preview) work
  D5  representative writes are refused with 403 and the demo message
  D6  the audit chain event count is unchanged after every attempted write
  D7  demo mode makes no outbound calls: the market feed returns no sample seeds
  D8  without the flag the middleware does not block writes
"""

from __future__ import annotations

import os
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "backend"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

_tmp = tempfile.mkdtemp(prefix="arbiter-demo-gate-")
os.environ["ARBITER_POLICY_PATH"] = os.path.join(_tmp, "policy.json")

import seed_demo  # noqa: E402

MESSAGE = "This is a read-only demo of Arbiter."


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)
    print(f"[PASS] {message}")


def main() -> int:
    db = os.path.join(_tmp, "demo.db")
    check(seed_demo.main(["--db", db]) == 0, "D1 demo database seeds offline from the committed fixtures")

    from fastapi.testclient import TestClient

    from app import feeds
    from app.server import app, resolution_store as store

    check(store.verify_audit_chain()["ok"] is True, "D1 audit chain verifies after seeding")
    decisions = [d for d in store.audit_log(limit=5000) if d["action"].startswith("decision")]
    check(bool(decisions), "D1 the example decision is recorded in the audit chain")

    from app import main as app_main

    os.environ["ARBITER_DEMO_MODE"] = "1"
    app_main._CACHE["reports"] = None  # a hosted demo process starts cold, with the flag already set
    try:
        client = TestClient(app)
        health = client.get("/api/health")
        check(health.status_code == 200 and health.json().get("demo_mode") is True, "D2 health reports demo_mode")

        for path in (
            "/api/overview",
            "/api/work-queue",
            "/api/precedents?include_inactive=true",
            "/api/audit/overview",
        ):
            r = client.get(path)
            check(r.status_code == 200, f"D3 GET {path} -> 200")
        queue = client.get("/api/work-queue").json()
        found = client.get("/api/audit/contracts", params={"q": "KXXISUCCESSOR"}).json()["contracts"]
        xi = found[0]["contract_id"]
        r = client.get(f"/api/audit/lineage/{xi}")
        check(r.status_code == 200, f"D3 GET /api/audit/lineage/{xi} -> 200")
        seeds = {m["ticker"] for m in feeds._sample("sample_markets.json")}
        check(
            not any(t in str(i) for i in queue["items"] for t in seeds),
            "D7 the queue holds only captured venue markets, no built-in sample seeds",
        )
        check(feeds.get_markets(live=True) == [], "D7 the market feed makes no live call and returns no samples")

        before = store.verify_audit_chain()["events"]
        cluster = client.get("/api/overview").json()["agent_brief"]["operations_intelligence"]["clusters"][0]
        r = client.post("/api/ask", json={"question": "Do acting leaders count?"})
        check(r.status_code == 200, "D4 POST /api/ask (read-only query) is allowed")
        r = client.post(
            "/api/decisions/consistency",
            json={"cluster_id": cluster["cluster_id"], "selection": "Acting leaders do not count"},
        )
        check(r.status_code == 200, "D4 POST /api/decisions/consistency (preview) is allowed")

        writes = [
            ("/api/decisions", {"cluster_id": cluster["cluster_id"], "selection": "x", "rationale": "x"}),
            (f"/api/work-queue/{queue['items'][0]['id']}", {"status": "in_progress"}),
            ("/api/audit/anchor", {"note": "demo"}),
            ("/api/audit/package", None),
            ("/api/audit/engagements", {"name": "demo"}),
            ("/api/appeals/check", {"contract_id": xi, "requested_selection": "x"}),
        ]
        for path, body in writes:
            r = client.post(path, json=body) if body is not None else client.post(path)
            check(r.status_code == 403 and r.json() == {"detail": MESSAGE}, f"D5 POST {path} -> 403 read-only")
        for method in ("put", "patch", "delete"):
            r = getattr(client, method)("/api/policy")
            check(r.status_code == 403, f"D5 {method.upper()} /api/policy -> 403")

        after = store.verify_audit_chain()
        check(after["ok"] is True and after["events"] == before, f"D6 audit chain unchanged ({before} events)")
    finally:
        os.environ.pop("ARBITER_DEMO_MODE", None)

    client = TestClient(app)
    check(
        client.get("/api/health").json().get("demo_mode") is False, "D8 health reports demo_mode false without the flag"
    )
    r = client.post("/api/audit/anchor", json={"note": "gate"})
    check(r.status_code != 403, f"D8 without the flag a write is not blocked by the middleware ({r.status_code})")
    print("DEMO MODE GATE: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
