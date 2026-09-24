#!/usr/bin/env python3
"""Collect dual-listed events from a seed list, fetching named markets by id at
each venue. This is the only collector that reaches the network by identifier
rather than by paging settled markets.

    python3 scripts/collect_targeted_candidates.py \
        benchmarks/seeds/dual_listed_seeds.jsonl \
        --out benchmarks/candidates_targeted_v0_2.jsonl \
        --coverage benchmarks/coverage_targeted_v0_2.json \
        --sleep 0.5

Network failures against a single identifier are recorded in the coverage report
and do not abort the run. Run offline-safe with --dry-run to validate the seed
file structure without fetching.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.real_benchmark.collectors import fetch_kalshi_market, fetch_polymarket_market
from app.real_benchmark.hashing import read_jsonl, write_jsonl
from app.real_benchmark.targeted import Seed, collect_targeted


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("seeds", help="seed JSONL: one row per real-world question")
    ap.add_argument("--out", default="benchmarks/candidates_targeted_v0_2.jsonl")
    ap.add_argument("--coverage", default=None, help="write per-seed coverage JSON here")
    ap.add_argument("--sleep", type=float, default=0.0, help="seconds between fetches")
    ap.add_argument("--dry-run", action="store_true", help="validate seeds; do not fetch")
    args = ap.parse_args()

    src = ROOT / args.seeds if not Path(args.seeds).is_absolute() else Path(args.seeds)
    seed_rows = read_jsonl(src)

    if args.dry_run:
        ok, bad = 0, []
        for i, r in enumerate(seed_rows, 1):
            try:
                s = Seed.from_row(r)
                if not (s.kalshi or s.polymarket):
                    bad.append(f"row {i} ({s.seed_event_id}): no venue identifiers")
                else:
                    ok += 1
            except Exception as exc:  # noqa: BLE001
                bad.append(f"row {i}: {exc}")
        print(json.dumps({"seeds": len(seed_rows), "valid": ok, "problems": bad}, indent=2))
        sys.exit(1 if bad else 0)

    def k(ident):
        if args.sleep:
            time.sleep(args.sleep)
        return fetch_kalshi_market(ident)

    def p(ident):
        if args.sleep:
            time.sleep(args.sleep)
        return fetch_polymarket_market(ident)

    result = collect_targeted(seed_rows, fetch_kalshi=k, fetch_polymarket=p)

    out = ROOT / args.out if not Path(args.out).is_absolute() else Path(args.out)
    write_jsonl(out, result["rows"])
    if args.coverage:
        cov = ROOT / args.coverage if not Path(args.coverage).is_absolute() else Path(args.coverage)
        cov.parent.mkdir(parents=True, exist_ok=True)
        cov.write_text(
            json.dumps({"coverage": result["coverage"], "summary": result["summary"]}, indent=2), encoding="utf-8"
        )

    for c in result["coverage"]:
        flag = "  <-- DISAGREEMENT" if c["outcome_disagreement"] else ("  (dual)" if c["dual_listed"] else "")
        print(
            f"{c['seed_event_id']:32s} K:{c['kalshi_outcomes'] or '-'} P:{c['polymarket_outcomes'] or '-'}{flag}",
            file=sys.stderr,
        )
    result["summary"]["output"] = str(out)
    print(json.dumps(result["summary"], indent=2))


if __name__ == "__main__":
    main()
