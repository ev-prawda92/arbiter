#!/usr/bin/env python3
"""Classify a collected candidate pool into v0.2 hardness classes in bulk.

    python3 scripts/classify_hardness.py \
        benchmarks/candidates_v0_2_raw.jsonl \
        --out benchmarks/candidates_v0_2_classified.jsonl \
        --report benchmarks/hardness_report_v0_2.json \
        --min-score 0.3

Reads candidates (from collect_holdout_candidates.py / collect_targeted), writes
each row annotated with its class + reasons, and a distribution report. Optionally
filters to rows at or above --min-score for the hard classes.
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

from app.real_benchmark.hardness import classify_pool
from app.real_benchmark.hashing import read_jsonl, write_jsonl


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("candidates")
    ap.add_argument("--out", default=None, help="annotated candidates JSONL")
    ap.add_argument("--report", default=None, help="distribution report JSON")
    ap.add_argument("--only-class", default=None, help="keep only this primary_class in --out")
    ap.add_argument("--min-score", type=float, default=0.0)
    args = ap.parse_args()

    src = ROOT / args.candidates if not Path(args.candidates).is_absolute() else Path(args.candidates)
    rows = read_jsonl(src)
    result = classify_pool(rows)

    kept = [c for c in result["classified"] if c["hardness_score"] >= args.min_score]
    if args.only_class:
        kept = [c for c in kept if c["primary_class"] == args.only_class]

    if args.out:
        out = ROOT / args.out if not Path(args.out).is_absolute() else Path(args.out)
        write_jsonl(out, kept)
        result["summary"]["output"] = str(out)
        result["summary"]["kept"] = len(kept)
    if args.report:
        rep = ROOT / args.report if not Path(args.report).is_absolute() else Path(args.report)
        rep.parent.mkdir(parents=True, exist_ok=True)
        rep.write_text(json.dumps(result["summary"], indent=2), encoding="utf-8")

    print(json.dumps(result["summary"], indent=2))


if __name__ == "__main__":
    main()
