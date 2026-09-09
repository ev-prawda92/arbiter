from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import BENCHMARK_VERSION
from .dataset import verify_dataset
from .runner import verify_prediction_run


def default_dataset_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "benchmarks" / "arb_gold_holdout_v0_1"


def default_runs_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "real_benchmark_runs"


def posture(dataset_dir: str | Path | None = None, runs_dir: str | Path | None = None) -> dict[str, Any]:
    dataset_root = Path(dataset_dir) if dataset_dir else default_dataset_dir()
    runs_root = Path(runs_dir) if runs_dir else default_runs_dir()
    verification = verify_dataset(dataset_root)
    latest: dict[str, Any] | None = None
    if runs_root.exists():
        candidates = sorted((p for p in runs_root.iterdir() if p.is_dir() and (p / "run_manifest.json").exists()), key=lambda p: p.stat().st_mtime, reverse=True)
        if candidates:
            try:
                run_manifest = json.loads((candidates[0] / "run_manifest.json").read_text(encoding="utf-8"))
                latest = {"run_dir": str(candidates[0]), **run_manifest}
            except Exception:
                latest = {"run_dir": str(candidates[0]), "invalid_manifest": True}
    return {
        "version": BENCHMARK_VERSION,
        "program": "ARB-GOLD-HOLDOUT-v0.1",
        "target_cases": 75,
        "dataset_state": verification.get("state"),
        "dataset_frozen": verification.get("ok") and verification.get("state") == "FROZEN",
        "case_count": verification.get("case_count", 0),
        "dataset_sha256": verification.get("dataset_sha256"),
        "dataset_errors": verification.get("errors", []),
        "latest_run": latest,
        "labels_separated_from_inputs": True,
        "blind_run_required": True,
        "tune_on_holdout": False,
        "production_settlement_certified": False,
        "next_action": "Collect and curate 50–100 resolved real contracts, then freeze ARB-GOLD-HOLDOUT-v0.1." if not verification.get("ok") else "Run Arbiter blind, pin predictions, then score labels/evidence coverage.",
    }
