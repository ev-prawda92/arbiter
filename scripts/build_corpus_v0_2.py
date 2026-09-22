#!/usr/bin/env python3
"""One-shot v0.2 corpus pipeline: collect -> classify -> join -> report.

Runs the whole scaling path in one command, against the live venue APIs (so run
it in a normal terminal with network, not the bridge shell). Collection uses the
patched collector, which now queries BOTH Kalshi hosts (external-api and
api.elections) plus Polymarket.

    python3 scripts/build_corpus_v0_2.py --limit-per-venue 400

Stages, each writing into --out-dir (default benchmarks/v0_2):
  1. collect   -> candidates_raw.jsonl
  2. classify  -> candidates_classified.jsonl + hardness_report.json
  3. join      -> cross_venue_pairs.jsonl
  4. report    -> pipeline_report.json + a printed quota-fill table

--skip-collect reuses an existing candidates file (--candidates) so stages 2-4
can be re-run offline without re-hitting the network.
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

from app.real_benchmark.collectors import collect_kalshi, collect_polymarket, dedupe_candidates
from app.real_benchmark.cross_venue import join_candidates
from app.real_benchmark.hardness import classify_pool
from app.real_benchmark.hashing import read_jsonl, write_jsonl

# Pivoted v0.2 targets (see HARD_CORPUS_V0_2.md). interpretive is filled by
# triage of hints, so its "auto" fill is reported as hints, not a primary count.
QUOTAS = {
    "interpretive_criteria": 35,
    "disputed": 25,
    "revised_source": 15,
    "multi_source_conflict": 8,
    "late_or_void": 7,
    "cross_venue_disagreement": 5,
    "control_easy": 5,
}


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit-per-venue", type=int, default=400)
    ap.add_argument("--out-dir", default="benchmarks/v0_2")
    ap.add_argument("--sleep", type=float, default=0.2, help="seconds between API pages")
    ap.add_argument("--min-confidence", type=float, default=0.35, help="cross-venue join threshold")
    ap.add_argument("--skip-collect", action="store_true")
    ap.add_argument("--candidates", default=None, help="existing candidates JSONL when --skip-collect")
    args = ap.parse_args()

    out = ROOT / args.out_dir if not Path(args.out_dir).is_absolute() else Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    raw_path = out / "candidates_raw.jsonl"

    # --- 1. collect ---
    if args.skip_collect:
        src = Path(args.candidates) if args.candidates else raw_path
        src = ROOT / src if not src.is_absolute() else src
        rows = read_jsonl(src)
        _log(f"[1/4] skip-collect: loaded {len(rows)} candidates from {src}")
    else:
        _log(f"[1/4] collecting up to {args.limit_per_venue}/venue (Kalshi x2 hosts + Polymarket)...")
        rows = []
        try:
            k = collect_kalshi(args.limit_per_venue, include_historical=True, sleep_seconds=args.sleep)
            _log(f"      kalshi: {len(k)}")
            rows.extend(k)
        except Exception as exc:  # noqa: BLE001
            _log(f"      kalshi FAILED: {exc}")
        try:
            p = collect_polymarket(args.limit_per_venue, sleep_seconds=args.sleep)
            _log(f"      polymarket: {len(p)}")
            rows.extend(p)
        except Exception as exc:  # noqa: BLE001
            _log(f"      polymarket FAILED: {exc}")
        rows = dedupe_candidates(rows)
        write_jsonl(raw_path, rows)
        _log(f"      wrote {len(rows)} deduped candidates -> {raw_path}")

    if not rows:
        _log("no candidates collected; aborting. (Network? Run in a terminal with internet.)")
        print(json.dumps({"error": "no candidates", "stage": "collect"}, indent=2))
        sys.exit(1)

    # --- 2. classify ---
    _log("[2/4] classifying hardness...")
    cls = classify_pool(rows)
    write_jsonl(out / "candidates_classified.jsonl", cls["classified"])
    (out / "hardness_report.json").write_text(json.dumps(cls["summary"], indent=2), encoding="utf-8")
    dist = cls["summary"]["distribution"]

    # --- 3. cross-venue join ---
    _log("[3/4] cross-venue join...")
    joined = join_candidates(rows, min_confidence=args.min_confidence)
    write_jsonl(out / "cross_venue_pairs.jsonl", joined["pairs"])
    disagreements = joined["summary"]["by_class"].get("outcome_disagreement", 0)

    # --- 4. consolidated report + quota table ---
    _log("[4/4] report")
    fill = {}
    for cls_name, target in QUOTAS.items():
        if cls_name == "cross_venue_disagreement":
            have = disagreements
        elif cls_name == "interpretive_criteria":
            have = cls["summary"].get("interpretive_hints", 0)  # candidates for triage
        else:
            have = dist.get(cls_name, 0)
        fill[cls_name] = {"have": have, "target": target, "gap": max(0, target - have)}

    report = {
        "candidates": len(rows),
        "hardness_distribution": dist,
        "interpretive_hints": cls["summary"].get("interpretive_hints", 0),
        "needs_review": cls["summary"].get("needs_review", 0),
        "cross_venue": joined["summary"]["by_class"],
        "quota_fill": fill,
        "outputs": {
            "candidates_raw": str(raw_path),
            "classified": str(out / "candidates_classified.jsonl"),
            "cross_venue_pairs": str(out / "cross_venue_pairs.jsonl"),
        },
    }
    (out / "pipeline_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("\n=== v0.2 quota fill ===", file=sys.stderr)
    print(f"{'class':26s} {'have':>5s} {'target':>7s} {'gap':>5s}", file=sys.stderr)
    for cls_name, f in fill.items():
        tag = " (hints->triage)" if cls_name == "interpretive_criteria" else ""
        print(f"{cls_name:26s} {f['have']:>5d} {f['target']:>7d} {f['gap']:>5d}{tag}", file=sys.stderr)

    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
