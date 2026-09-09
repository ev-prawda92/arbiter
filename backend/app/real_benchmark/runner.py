from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import PREDICTION_SCHEMA, BENCHMARK_VERSION
from .dataset import verify_dataset
from .hashing import canonical_json, read_jsonl, sha256_file, sha256_text, write_jsonl
from .resolver import resolve_from_compiled_spec


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _market(contract: dict[str, Any]) -> dict[str, Any]:
    return {
        "ticker": contract["case_id"],
        "title": contract.get("title", ""),
        "subtitle": "",
        "category": contract.get("category") or "uncategorized",
        "rules_primary": contract.get("rules", ""),
        "rules_secondary": "",
        "open_interest": 0,
    }


def _authority_catalog_from_store(authorities: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    return list(authorities or [])


def _evidence_by_case(root: Path, manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    # BENCHMARK CONTROL: evidence is an input artifact and is physically
    # separate from labels. It may contain observations that allow the compiled
    # rule to be evaluated, but it cannot contain the venue's outcome label.
    evidence_path = root / manifest["files"]["evidence"]
    return {str(row.get("case_id")): row for row in read_jsonl(evidence_path)}


def run_blind(
    dataset_dir: str | Path,
    output_dir: str | Path,
    *,
    engine_module,
    compiler_module,
    semantic_module,
    policy: dict[str, Any],
    authorities: list[dict[str, Any]] | None = None,
    run_name: str = "blind-run",
) -> dict[str, Any]:
    verification = verify_dataset(dataset_dir)
    if not verification["ok"]:
        raise ValueError("dataset verification failed before blind run: " + "; ".join(verification["errors"]))
    root = Path(dataset_dir)
    manifest = verification["manifest"]
    # BENCHMARK CONTROL: this function intentionally never resolves or opens the
    # manifest's labels path. Only blind contracts + independent evidence inputs
    # are loaded during prediction.
    contracts_path = root / manifest["files"]["contracts"]
    contracts = read_jsonl(contracts_path)
    evidence_by_case = _evidence_by_case(root, manifest)
    auth = _authority_catalog_from_store(authorities)
    started_at = _now()
    predictions: list[dict[str, Any]] = []
    for contract in contracts:
        sem = semantic_module.analyze_contract(contract.get("title", ""), contract.get("rules", ""))
        comp = compiler_module.compile_rules(
            contract_id=f"bench_{contract['case_id']}",
            title=contract.get("title", ""),
            rules=contract.get("rules", ""),
            known_authorities=auth,
            metadata={
                "benchmark_dataset": manifest.get("name"),
                "benchmark_case_id": contract["case_id"],
                "benchmark_blind": True,
            },
        )
        integrity = engine_module.analyze(_market(contract), policy)
        evidence = evidence_by_case.get(str(contract["case_id"]))
        resolution = resolve_from_compiled_spec(comp, evidence)
        predictions.append({
            "case_id": contract["case_id"],
            "venue": contract.get("venue"),
            "category": contract.get("category"),
            "compiler_status": comp.get("status"),
            "semantic_status": sem.get("status"),
            "unresolved_fields": comp.get("unresolved_fields", []),
            "semantic_unresolved_fields": sem.get("unresolved_semantic_fields", []),
            "engine_verdict": (integrity.get("verdict") or {}).get("key"),
            "engine_verdict_label": (integrity.get("verdict") or {}).get("label"),
            "composite": integrity.get("composite"),
            "source_score": ((integrity.get("levers") or {}).get("source") or {}).get("score"),
            "timing_score": ((integrity.get("levers") or {}).get("timing") or {}).get("score"),
            "definition_score": ((integrity.get("levers") or {}).get("definition") or {}).get("score"),
            "source_flags": ((integrity.get("levers") or {}).get("source") or {}).get("flags", []),
            "timing_flags": ((integrity.get("levers") or {}).get("timing") or {}).get("flags", []),
            "definition_flags": ((integrity.get("levers") or {}).get("definition") or {}).get("flags", []),
            "semantic_hash": sem.get("semantic_hash"),
            "compilation_hash": comp.get("compilation_hash"),
            "predicted_outcome": resolution.get("predicted_outcome"),
            "outcome_prediction_reason": resolution.get("reason"),
            "resolution_method": resolution.get("resolution_method"),
            "evidence_present": evidence is not None,
            "evidence_raw_sha256": evidence.get("raw_sha256") if evidence else None,
            "evidence_source_url": evidence.get("source_url") if evidence else None,
            "evidence_authority": evidence.get("authority") if evidence else None,
            "resolution_trace": {k: v for k, v in resolution.items() if k not in {"predicted_outcome", "reason", "resolution_method"}},
        })
    completed_at = _now()
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    predictions_path = out / "predictions.jsonl"
    write_jsonl(predictions_path, predictions)
    predictions_hash = sha256_file(predictions_path)
    run_manifest = {
        "schema": PREDICTION_SCHEMA,
        "benchmark_version": BENCHMARK_VERSION,
        "run_name": run_name,
        "started_at": started_at,
        "completed_at": completed_at,
        "dataset": manifest.get("name"),
        "dataset_sha256": manifest["hashes"]["dataset_sha256"],
        "contracts_sha256": manifest["hashes"]["contracts_sha256"],
        "evidence_sha256": manifest["hashes"]["evidence_sha256"],
        "case_count": len(predictions),
        "evidence_case_count": len(evidence_by_case),
        "labels_loaded_during_run": False,
        "evidence_loaded_during_run": True,
        "predictions_sha256": predictions_hash,
        "policy_version": policy.get("version"),
        "engine": "deterministic-resolution-integrity",
        "outcome_resolver": "compiled-spec-evidence-v1",
        "compiler_version": getattr(compiler_module, "COMPILER_VERSION", None),
        "semantic_version": getattr(semantic_module, "SEMANTIC_VERSION", None),
        "status_counts": dict(Counter(str(x.get("compiler_status")) for x in predictions)),
        "outcome_counts": dict(Counter(str(x.get("predicted_outcome")) for x in predictions)),
        "run_sha256": None,
    }
    run_manifest["run_sha256"] = sha256_text(canonical_json({k: v for k, v in run_manifest.items() if k != "run_sha256"}))
    (out / "run_manifest.json").write_text(json.dumps(run_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"manifest": run_manifest, "predictions": predictions, "output_dir": str(out)}


def verify_prediction_run(dataset_dir: str | Path, run_dir: str | Path) -> dict[str, Any]:
    dataset = verify_dataset(dataset_dir)
    errors = list(dataset.get("errors") or []) if not dataset.get("ok") else []
    run_root = Path(run_dir)
    manifest_path = run_root / "run_manifest.json"
    predictions_path = run_root / "predictions.jsonl"
    if not manifest_path.exists():
        errors.append("run_manifest.json missing")
        return {"ok": False, "errors": errors}
    run_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if run_manifest.get("schema") != PREDICTION_SCHEMA:
        errors.append("unexpected prediction schema")
    if not predictions_path.exists():
        errors.append("predictions.jsonl missing")
    else:
        actual = sha256_file(predictions_path)
        if actual != run_manifest.get("predictions_sha256"):
            errors.append("predictions hash mismatch")
        rows = read_jsonl(predictions_path)
        if len(rows) != run_manifest.get("case_count"):
            errors.append("prediction case_count mismatch")
        forbidden = {"known_outcome", "settlement_value", "gold_status", "gold_unresolved_fields"}
        for row in rows:
            leaked = forbidden.intersection(row)
            if leaked:
                errors.append(f"prediction row contains labels for {row.get('case_id')}: {sorted(leaked)}")
            if row.get("predicted_outcome") not in {"YES", "NO", "HOLD"}:
                errors.append(f"invalid predicted_outcome for {row.get('case_id')}")
    if dataset.get("ok"):
        dmanifest = dataset.get("manifest") or {}
        if run_manifest.get("dataset_sha256") != dataset.get("dataset_sha256"):
            errors.append("run pinned to different dataset hash")
        if run_manifest.get("contracts_sha256") != (dmanifest.get("hashes") or {}).get("contracts_sha256"):
            errors.append("run pinned to different contracts hash")
        if run_manifest.get("evidence_sha256") != (dmanifest.get("hashes") or {}).get("evidence_sha256"):
            errors.append("run pinned to different evidence hash")
        expected_count = dataset.get("case_count")
        if run_manifest.get("case_count") != expected_count:
            errors.append("run case_count differs from dataset")
    expected_run_hash = sha256_text(canonical_json({k: v for k, v in run_manifest.items() if k != "run_sha256"}))
    if run_manifest.get("run_sha256") != expected_run_hash:
        errors.append("run manifest hash mismatch")
    if run_manifest.get("labels_loaded_during_run") is not False:
        errors.append("run does not attest label separation")
    if run_manifest.get("evidence_loaded_during_run") is not True:
        errors.append("run does not attest evidence input usage")
    return {"ok": not errors, "errors": errors, "run_manifest": run_manifest, "dataset": dataset}
