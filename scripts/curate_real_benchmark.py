#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.real_benchmark.curation import curate_candidates, read_jsonl, write_jsonl


def main() -> None:
    ap = argparse.ArgumentParser(description="Curate real-world benchmark candidates before freezing a holdout.")
    ap.add_argument("input", help="Candidate JSONL produced by collect_holdout_candidates.py")
    ap.add_argument("--out", required=True, help="Output JSONL containing accepted benchmark-quality candidates")
    ap.add_argument("--rejected", help="Optional JSONL containing rejected candidates with reasons")
    ap.add_argument("--report", help="Optional JSON summary path")
    ap.add_argument("--min-score", type=int, default=80)
    args = ap.parse_args()

    if not 0 <= args.min_score <= 100:
        raise SystemExit("--min-score must be between 0 and 100")

    rows = read_jsonl(args.input)
    result = curate_candidates(rows, min_score=args.min_score)
    write_jsonl(args.out, result["accepted"])
    if args.rejected:
        write_jsonl(args.rejected, result["rejected"])

    summary = {k: v for k, v in result.items() if k not in {"accepted", "rejected"}}
    if args.report:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(json.dumps(summary, indent=2, sort_keys=True))
    if result["accepted_count"] == 0:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
