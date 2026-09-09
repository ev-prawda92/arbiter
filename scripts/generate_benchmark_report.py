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

from app.real_benchmark.report import score_run


def main() -> None:
    ap = argparse.ArgumentParser(description="Score a hash-pinned blind run after prediction completion and generate Markdown/JSON benchmark reports.")
    ap.add_argument("dataset")
    ap.add_argument("run_dir")
    ap.add_argument("--out")
    args = ap.parse_args()
    dataset = Path(args.dataset)
    run_dir = Path(args.run_dir)
    if not dataset.is_absolute():
        dataset = ROOT / dataset
    if not run_dir.is_absolute():
        run_dir = ROOT / run_dir
    out = Path(args.out) if args.out else run_dir / "report"
    if not out.is_absolute():
        out = ROOT / out
    result = score_run(dataset, run_dir, out)
    print(json.dumps(result["report"], indent=2, sort_keys=True))
    print(f"Markdown: {result['markdown_path']}")


if __name__ == "__main__":
    main()
