#!/usr/bin/env python3
"""Pull watched Kalshi and Polymarket markets into Arbiter.

Run from a machine that can reach the venue APIs:

    python3 scripts/sync_venues.py --discover --dry-run
    python3 scripts/sync_venues.py --discover
    python3 scripts/sync_venues.py --watchlist benchmarks/seeds/dual_listed_seeds_v0_2.jsonl

--discover scans currently OPEN markets on both venues and brings in only the
ones the hardness classifier says need a human judgment (interpretive wording,
disputes, revision-prone data, contested official sources). Without it, the
markets in --watchlist are synced (default: the v0.2 benchmark seeds). Either way
it writes to
the same database the app uses (ARBITER_DATABASE_PATH, else
backend/data/arbiter.db). Start the app afterwards and the markets that need a
human judgment are in the work queue and the decision workbench.

Kalshi discovery walks open EVENTS and filters by event category (Sports is
excluded by default, since Kalshi's flat market list is mostly sports):
    --kalshi-categories "Politics,Elections,Economics"   only these categories
    --kalshi-exclude "Sports,Entertainment"             skip these (default: Sports)
    --kalshi-source markets                             old flat market scan

--retriage closes open intake work items the current classifier no longer
flags (only items nobody has touched; decisions and operator changes win).
It can run alone or with a sync.

--dry-run fetches and classifies but writes nothing.
--save-raw DIR keeps each raw API response (JSON) for audit or offline replay.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "backend"))

from app import venue_intake  # noqa: E402
from app.resolution_infra import DB_PATH, ResolutionStore  # noqa: E402

DEFAULT_WATCHLIST = os.path.join(ROOT, "benchmarks", "seeds", "dual_listed_seeds_v0_2.jsonl")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--watchlist", default=DEFAULT_WATCHLIST, help="seeds JSONL of markets to watch")
    ap.add_argument("--db", default=DB_PATH, help="Arbiter database (default: the app's)")
    ap.add_argument(
        "--discover",
        nargs="?",
        type=int,
        const=200,
        metavar="N",
        help="scan up to N open markets per venue (default 200) instead of a watchlist",
    )
    ap.add_argument(
        "--include-all", action="store_true", help="with --discover, also track markets needing no judgment"
    )
    ap.add_argument(
        "--kalshi-source",
        choices=("events", "markets"),
        default="events",
        help="Kalshi discovery via open events by category (default) or the flat market list",
    )
    ap.add_argument(
        "--kalshi-categories", default="", help="comma-separated Kalshi categories to include (default: all)"
    )
    ap.add_argument(
        "--kalshi-exclude", default="Sports", help="comma-separated Kalshi categories to skip (default: Sports)"
    )
    ap.add_argument(
        "--retriage", action="store_true", help="close untouched intake work the current classifier no longer flags"
    )
    ap.add_argument("--no-sync", action="store_true", help="with --retriage, skip fetching (offline)")
    ap.add_argument("--dry-run", action="store_true", help="fetch and classify only; write nothing")
    ap.add_argument("--save-raw", metavar="DIR", help="save each raw API response to DIR")
    ap.add_argument("--json", action="store_true", help="print the full report as JSON")
    args = ap.parse_args()

    if args.retriage and args.no_sync:
        tri = venue_intake.retriage(ResolutionStore(args.db), dry_run=args.dry_run)
        print_retriage(tri, args.dry_run)
        return 0

    fetcher = venue_intake.fetch_live
    if args.save_raw:
        os.makedirs(args.save_raw, exist_ok=True)

        def fetcher(venue: str, market_id: str):  # noqa: F811
            raw, url = venue_intake.fetch_live(venue, market_id)
            path = os.path.join(args.save_raw, f"{venue}-{market_id}.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump({"url": url, "raw": raw}, fh, indent=2, sort_keys=True)
            return raw, url

    stats = None
    boilerplate = None
    if args.discover:
        cats = [c for c in args.kalshi_categories.split(",") if c.strip()]
        excl = [c for c in args.kalshi_exclude.split(",") if c.strip()]

        def lister(venue: str, limit: int):
            return venue_intake.list_open_live(
                venue, limit, kalshi_source=args.kalshi_source, categories=cats, exclude=excl
            )

        events, fetcher, stats = venue_intake.discover(lister, limit=args.discover, include_all=args.include_all)
        boilerplate = stats["boilerplate"]
        if args.save_raw:
            cached = fetcher

            def fetcher(venue: str, market_id: str):  # noqa: F811
                raw, url = cached(venue, market_id)
                with open(os.path.join(args.save_raw, f"{venue}-{market_id}.json"), "w", encoding="utf-8") as fh:
                    json.dump({"url": url, "raw": raw}, fh, indent=2, sort_keys=True)
                return raw, url
    else:
        events = venue_intake.load_watchlist(args.watchlist)
    store = ResolutionStore(args.db)
    report = venue_intake.sync(store, events, fetcher=fetcher, dry_run=args.dry_run, boilerplate=boilerplate)

    if args.json:
        print(json.dumps(report, indent=2, default=str))
        return 1 if report["errors"] and not report["markets"] else 0

    mode = "DRY RUN (nothing written)" if args.dry_run else f"database: {args.db}"
    print(f"Arbiter venue sync {report['version']} - {mode}")
    if stats:
        scanned = ", ".join(f"{v} {n}" for v, n in stats["scanned"].items()) or "none"
        flagged = ", ".join(f"{v} {n}" for v, n in stats["flagged"].items()) or "none"
        print(f"discover: scanned open markets ({scanned}); need a human judgment ({flagged})")
        for v, err in stats["errors"].items():
            print(f"discover: {v} unavailable - {err}")
        for v, cats_seen in stats.get("by_category", {}).items():
            parts = [
                f"{c} {n['flagged']}/{n['scanned']}"
                for c, n in sorted(cats_seen.items(), key=lambda x: -x[1]["scanned"])
            ]
            print(f"  {v} by category (flagged/scanned): " + ", ".join(parts))
    print(f"{len(events)} events, {sum(len(e.markets) for e in events)} markets\n")
    for m in report["markets"]:
        outcome = m.get("outcome") or "-"
        needs = m.get("review_class") or "no human judgment needed"
        work = f"  work item: {m['work_item']}" if "work_item" in m else ""
        title = (m.get("title") or "")[:60]
        print(f"  {m['venue']:<10} {m['market_id']:<28} {m['status']:<7} {outcome:<4} {needs:<22} {title}{work}")
    for e in report["errors"]:
        print(f"  {e['venue']:<10} {e['market_id']:<32} ERROR  {e['error']}")
    for ev in report["events"]:
        if ev.get("cross_venue"):
            print(f"\n  cross-venue [{ev['event']}]: {ev['cross_venue']} {ev['settled']}")
    t = report["totals"]
    if args.retriage:
        print_retriage(venue_intake.retriage(store, boilerplate=boilerplate, dry_run=args.dry_run), args.dry_run)
    verb = "would sync" if args.dry_run else "synced"
    print(
        f"\n{t['markets']} {verb}, {t['errors']} errors · work items opened {t['work_items_opened']}, "
        f"closed {t['work_items_closed']} · evidence appended {t['evidence_appended']} · "
        f"cross-venue disagreements {t['cross_venue_disagreements']}"
    )
    return 1 if report["errors"] and not report["markets"] else 0


def print_retriage(tri: dict, dry_run: bool) -> None:
    verb = "would close" if dry_run else "closed"
    t = tri["totals"]
    print(
        f"\nre-triage: checked {tri['checked']} open intake items · {verb} {t['closed']} · "
        f"still flagged {t['kept']} · left alone (touched) {t['skipped']}"
    )
    for c in tri["closed"][:40]:
        print(f"  {verb:<11} {c['kind']:<18} {c['subject']:<34} {(c.get('title') or '')[:50]}")
    if len(tri["closed"]) > 40:
        print(f"  ... and {len(tri['closed']) - 40} more")


if __name__ == "__main__":
    raise SystemExit(main())
