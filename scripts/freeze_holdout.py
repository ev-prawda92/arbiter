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

from app.real_benchmark.dataset import freeze_candidates
from app.real_benchmark.hashing import read_jsonl


def main() -> None:
    ap = argparse.ArgumentParser(description="Freeze an immutable, label-separated real-contract holdout.")
    ap.add_argument("candidates", help="candidate JSONL produced by collect_holdout_candidates.py or curated manually")
    ap.add_argument("--out", default="benchmarks/arb_gold_holdout_v0_1")
    ap.add_argument("--target", type=int, default=75)
    ap.add_argument("--seed", default="ARB-GOLD-HOLDOUT-v0.1")
    ap.add_argument("--name", default="ARB-GOLD-HOLDOUT-v0.1")
    ap.add_argument("--created-by", default="benchmark-curator")
    ap.add_argument("--min-rules-chars", type=int, default=40)
    args = ap.parse_args()
    candidates_path = Path(args.candidates)
    if not candidates_path.is_absolute():
        candidates_path = ROOT / candidates_path
    out = Path(args.out)
    if not out.is_absolute():
        out = ROOT / out
    manifest = freeze_candidates(
        read_jsonl(candidates_path), out, name=args.name, target=args.target,
        seed=args.seed, created_by=args.created_by, min_rules_chars=args.min_rules_chars,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    print("\nIMPORTANT: Do not tune Arbiter against this dataset. Fixes discovered here belong on a future holdout version.")


if __name__ == "__main__":
    main()
