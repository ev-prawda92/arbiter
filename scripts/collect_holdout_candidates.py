#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.real_benchmark.collectors import collect_kalshi, collect_polymarket, dedupe_candidates
from app.real_benchmark.hashing import write_jsonl


def main() -> None:
    ap = argparse.ArgumentParser(description="Collect resolved real-contract candidates. Collection does not freeze or validate a holdout.")
    ap.add_argument("--venue", action="append", choices=["kalshi", "polymarket"], required=True, help="repeat for multiple venues")
    ap.add_argument("--limit-per-venue", type=int, default=100)
    ap.add_argument("--out", default="benchmarks/candidates_v0_1.jsonl")
    ap.add_argument("--no-kalshi-historical", action="store_true")
    args = ap.parse_args()
    rows = []
    for venue in args.venue:
        if venue == "kalshi":
            data = collect_kalshi(args.limit_per_venue, include_historical=not args.no_kalshi_historical)
        else:
            data = collect_polymarket(args.limit_per_venue)
        print(f"{venue}: collected {len(data)} eligible resolved binary candidates", file=sys.stderr)
        rows.extend(data)
    rows = dedupe_candidates(rows)
    out = ROOT / args.out if not Path(args.out).is_absolute() else Path(args.out)
    write_jsonl(out, rows)
    summary = {
        "output": str(out),
        "candidate_count": len(rows),
        "venues": sorted(set(str(r.get("venue")) for r in rows)),
        "note": "Candidate collection is not a benchmark result. Review provenance and freeze separately.",
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
