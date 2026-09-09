#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app import compiler, engine, policy, semantic_contract
from app.resolution_infra import store, seed_reference_data
from app.real_benchmark.runner import run_blind


def main() -> None:
    ap = argparse.ArgumentParser(description="Run Arbiter blind against a frozen holdout. Labels are not read by the prediction runner.")
    ap.add_argument("dataset", nargs="?", default="benchmarks/arb_gold_holdout_v0_1")
    ap.add_argument("--out")
    ap.add_argument("--name", default="ARB-GOLD-HOLDOUT-v0.1-blind")
    args = ap.parse_args()
    dataset = Path(args.dataset)
    if not dataset.is_absolute():
        dataset = ROOT / dataset
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = Path(args.out) if args.out else ROOT / "backend" / "data" / "real_benchmark_runs" / stamp
    if not out.is_absolute():
        out = ROOT / out
    seed_reference_data()
    authorities = store.list_authorities()
    result = run_blind(
        dataset, out, engine_module=engine, compiler_module=compiler,
        semantic_module=semantic_contract, policy=policy.load_policy(),
        authorities=authorities, run_name=args.name,
    )
    print(json.dumps(result["manifest"], indent=2, sort_keys=True))
    print(f"Predictions: {out / 'predictions.jsonl'}")


if __name__ == "__main__":
    main()
