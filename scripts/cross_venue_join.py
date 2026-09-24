#!/usr/bin/env python3
"""Surface cross-venue candidate pairs (Kalshi x Polymarket) and flag outcome
disagreements. Reads an existing candidates JSONL (offline); does not collect.

Collection stays separate: run collect_holdout_candidates.py first, then join.

    python3 scripts/cross_venue_join.py \
        benchmarks/candidates_v0_1.jsonl \
        --min-confidence 0.35 \
        --out benchmarks/cross_venue_pairs_v0_2.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.real_benchmark.cross_venue import join_candidates
from app.real_benchmark.hashing import read_jsonl, write_jsonl


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("candidates", help="candidate JSONL from collect_holdout_candidates.py")
    ap.add_argument("--min-confidence", type=float, default=0.35)
    ap.add_argument("--left-venue", default="kalshi")
    ap.add_argument("--right-venue", default="polymarket")
    ap.add_argument("--out", default=None, help="write ranked pairs JSONL here")
    ap.add_argument("--show", type=int, default=10, help="print this many top pairs to stderr")
    args = ap.parse_args()

    src = ROOT / args.candidates if not Path(args.candidates).is_absolute() else Path(args.candidates)
    rows = read_jsonl(src)
    result = join_candidates(
        rows,
        min_confidence=args.min_confidence,
        left_venue=args.left_venue,
        right_venue=args.right_venue,
    )

    if args.out:
        out = ROOT / args.out if not Path(args.out).is_absolute() else Path(args.out)
        write_jsonl(out, result["pairs"])
        result["summary"]["output"] = str(out)

    for p in result["pairs"][: args.show]:
        print(
            f"[{p['pair_class']:22s} c={p['match_confidence']:.2f}] "
            f"{p['left']['known_outcome']:3s} {p['left']['title'][:52]!r} "
            f"|| {p['right']['known_outcome']:3s} {p['right']['title'][:52]!r}",
            file=sys.stderr,
        )
    print(json.dumps(result["summary"], indent=2))


if __name__ == "__main__":
    main()
