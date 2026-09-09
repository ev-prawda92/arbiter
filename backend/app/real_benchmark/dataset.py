from __future__ import annotations

import json
import random
import shutil
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from . import DATASET_SCHEMA, BENCHMARK_VERSION
from .hashing import canonical_json, read_jsonl, sha256_file, sha256_text, write_jsonl
from .schema import (
    contract_input_from_candidate, detect_label_leakage, evidence_from_candidate,
    label_from_candidate, provenance_from_candidate, validate_candidate,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _norm_category(row: dict[str, Any]) -> str:
    value = str(row.get("category") or "uncategorized").strip().lower()
    return value[:80] or "uncategorized"


def stratified_select(candidates: list[dict[str, Any]], target: int, seed: str) -> list[dict[str, Any]]:
    if target <= 0:
        raise ValueError("target must be positive")
    if len(candidates) <= target:
        return sorted(candidates, key=lambda r: (str(r.get("venue")), str(r.get("case_id"))))
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in candidates:
        groups[(str(row.get("venue") or "unknown"), _norm_category(row))].append(row)
    rng = random.Random(seed)
    ordered_keys = sorted(groups)
    for key in ordered_keys:
        rng.shuffle(groups[key])
    # Randomize deterministic group rotation so one lexicographically early
    # category does not always get the last slots.
    rng.shuffle(ordered_keys)
    selected: list[dict[str, Any]] = []
    while len(selected) < target:
        made_progress = False
        for key in ordered_keys:
            if groups[key]:
                selected.append(groups[key].pop())
                made_progress = True
                if len(selected) >= target:
                    break
        if not made_progress:
            break
    return sorted(selected, key=lambda r: str(r.get("case_id")))


def freeze_candidates(
    candidates: Iterable[dict[str, Any]],
    dataset_dir: str | Path,
    *,
    name: str = "ARB-GOLD-HOLDOUT-v0.1",
    target: int = 75,
    seed: str = "ARB-GOLD-HOLDOUT-v0.1",
    created_by: str = "benchmark-curator",
    min_rules_chars: int = 40,
) -> dict[str, Any]:
    root = Path(dataset_dir)
    marker = root / "FROZEN.sha256"
    if marker.exists() or (root / "manifest.json").exists():
        raise FileExistsError(f"dataset already frozen at {root}; create a new dataset version rather than overwriting it")

    valid: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    rejected: list[dict[str, Any]] = []
    for raw in candidates:
        row = dict(raw)
        errors = validate_candidate(row, min_rules_chars=min_rules_chars)
        case_id = str(row.get("case_id") or "")
        if case_id in seen_ids:
            errors.append("duplicate case_id")
        if errors:
            rejected.append({"case_id": case_id or None, "errors": errors})
            continue
        seen_ids.add(case_id)
        valid.append(row)

    if len(valid) < target:
        raise ValueError(f"only {len(valid)} valid candidates available; target is {target}")

    selected = stratified_select(valid, target, seed)
    frozen_at = _now()
    contracts = [contract_input_from_candidate(r) for r in selected]
    labels = [label_from_candidate(r, frozen_at) for r in selected]
    provenance = [provenance_from_candidate(r) for r in selected]
    evidence = [e for r in selected if (e := evidence_from_candidate(r)) is not None]

    leakage = []
    for contract in contracts:
        leakage.extend(f"{contract['case_id']}:{x}" for x in detect_label_leakage(contract))
    if leakage:
        raise ValueError("label leakage detected in blind contract inputs: " + ", ".join(leakage[:8]))

    root.mkdir(parents=True, exist_ok=True)
    contracts_path = root / "contracts.jsonl"
    labels_path = root / "labels.jsonl"
    provenance_path = root / "provenance.jsonl"
    evidence_path = root / "evidence.jsonl"
    rejections_path = root / "rejections.json"
    write_jsonl(contracts_path, contracts)
    write_jsonl(labels_path, labels)
    write_jsonl(provenance_path, provenance)
    write_jsonl(evidence_path, evidence)
    rejections_path.write_text(json.dumps(rejected, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    contracts_hash = sha256_file(contracts_path)
    labels_hash = sha256_file(labels_path)
    provenance_hash = sha256_file(provenance_path)
    evidence_hash = sha256_file(evidence_path)
    selected_ids_hash = sha256_text(canonical_json([r["case_id"] for r in contracts]))
    dataset_hash = sha256_text(canonical_json({
        "schema": DATASET_SCHEMA,
        "name": name,
        "contracts_sha256": contracts_hash,
        "labels_sha256": labels_hash,
        "provenance_sha256": provenance_hash,
        "evidence_sha256": evidence_hash,
        "selected_case_ids_sha256": selected_ids_hash,
    }))
    venue_counts: dict[str, int] = defaultdict(int)
    category_counts: dict[str, int] = defaultdict(int)
    for row in contracts:
        venue_counts[str(row.get("venue"))] += 1
        category_counts[str(row.get("category") or "uncategorized")] += 1
    manifest = {
        "schema": DATASET_SCHEMA,
        "benchmark_version": BENCHMARK_VERSION,
        "name": name,
        "state": "FROZEN",
        "frozen_at": frozen_at,
        "created_by": created_by,
        "case_count": len(contracts),
        "target_case_count": target,
        "selection": {
            "method": "deterministic-stratified-round-robin",
            "seed_sha256": sha256_text(seed),
            "selected_case_ids_sha256": selected_ids_hash,
        },
        "venues": dict(sorted(venue_counts.items())),
        "categories": dict(sorted(category_counts.items())),
        "files": {
            "contracts": "contracts.jsonl",
            "labels": "labels.jsonl",
            "provenance": "provenance.jsonl",
            "evidence": "evidence.jsonl",
            "rejections": "rejections.json",
        },
        "hashes": {
            "contracts_sha256": contracts_hash,
            "labels_sha256": labels_hash,
            "provenance_sha256": provenance_hash,
            "evidence_sha256": evidence_hash,
            "dataset_sha256": dataset_hash,
        },
        "benchmark_controls": {
            "labels_separated_from_inputs": True,
            "evidence_separated_from_labels": True,
            "evidence_case_count": len(evidence),
            "blind_runner_forbidden_from_loading_labels": True,
            "overwrite_frozen_dataset": False,
            "tune_on_holdout": False,
            "external_certification": False,
        },
    }
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    marker.write_text(dataset_hash + "\n", encoding="utf-8")
    return {**manifest, "rejected_candidates": len(rejected)}


def verify_dataset(dataset_dir: str | Path, *, require_frozen: bool = True) -> dict[str, Any]:
    root = Path(dataset_dir)
    manifest_path = root / "manifest.json"
    if not manifest_path.exists():
        return {"ok": False, "state": "NOT_FROZEN", "errors": ["manifest.json missing"], "dataset_dir": str(root)}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    errors: list[str] = []
    if manifest.get("schema") != DATASET_SCHEMA:
        errors.append(f"unexpected schema {manifest.get('schema')}")
    if require_frozen and manifest.get("state") != "FROZEN":
        errors.append("dataset state is not FROZEN")
    files = manifest.get("files") or {}
    expected_hashes = manifest.get("hashes") or {}
    resolved: dict[str, str] = {}
    for logical, hash_key in (("contracts", "contracts_sha256"), ("labels", "labels_sha256"), ("provenance", "provenance_sha256"), ("evidence", "evidence_sha256")):
        name = files.get(logical)
        if not name:
            errors.append(f"manifest missing files.{logical}")
            continue
        path = root / str(name)
        if not path.exists():
            errors.append(f"missing {name}")
            continue
        actual = sha256_file(path)
        resolved[hash_key] = actual
        if actual != expected_hashes.get(hash_key):
            errors.append(f"hash mismatch for {name}")
    if resolved.get("contracts_sha256") and resolved.get("labels_sha256") and resolved.get("provenance_sha256") and resolved.get("evidence_sha256"):
        dataset_hash = sha256_text(canonical_json({
            "schema": manifest.get("schema"),
            "name": manifest.get("name"),
            "contracts_sha256": resolved["contracts_sha256"],
            "labels_sha256": resolved["labels_sha256"],
            "provenance_sha256": resolved["provenance_sha256"],
            "evidence_sha256": resolved["evidence_sha256"],
            "selected_case_ids_sha256": (manifest.get("selection") or {}).get("selected_case_ids_sha256"),
        }))
        if dataset_hash != expected_hashes.get("dataset_sha256"):
            errors.append("dataset aggregate hash mismatch")
        marker = root / "FROZEN.sha256"
        if not marker.exists() or marker.read_text(encoding="utf-8").strip() != dataset_hash:
            errors.append("FROZEN.sha256 marker missing or mismatched")
    contracts = read_jsonl(root / str(files.get("contracts") or "contracts.jsonl")) if (root / str(files.get("contracts") or "contracts.jsonl")).exists() else []
    labels = read_jsonl(root / str(files.get("labels") or "labels.jsonl")) if (root / str(files.get("labels") or "labels.jsonl")).exists() else []
    provenance = read_jsonl(root / str(files.get("provenance") or "provenance.jsonl")) if (root / str(files.get("provenance") or "provenance.jsonl")).exists() else []
    evidence = read_jsonl(root / str(files.get("evidence") or "evidence.jsonl")) if (root / str(files.get("evidence") or "evidence.jsonl")).exists() else []
    contract_ids = [str(x.get("case_id")) for x in contracts]
    label_ids = [str(x.get("case_id")) for x in labels]
    provenance_ids = [str(x.get("case_id")) for x in provenance]
    if len(contract_ids) != len(set(contract_ids)):
        errors.append("duplicate case_id in contracts")
    if contract_ids != label_ids or contract_ids != provenance_ids:
        errors.append("contracts/labels/provenance case ordering differs")
    if len(contracts) != int(manifest.get("case_count") or -1):
        errors.append("case_count does not match contracts.jsonl")
    evidence_ids = [str(x.get("case_id")) for x in evidence]
    if len(evidence_ids) != len(set(evidence_ids)):
        errors.append("duplicate case_id in evidence")
    if not set(evidence_ids).issubset(set(contract_ids)):
        errors.append("evidence contains unknown case_id")
    declared_evidence_count = ((manifest.get("benchmark_controls") or {}).get("evidence_case_count"))
    if declared_evidence_count is not None and int(declared_evidence_count) != len(evidence):
        errors.append("evidence_case_count does not match evidence.jsonl")
    for ev in evidence:
        leakage = detect_label_leakage(ev)
        if leakage:
            errors.append(f"label leakage in evidence {ev.get('case_id')}: {', '.join(leakage[:4])}")
    for contract in contracts:
        leakage = detect_label_leakage(contract)
        if leakage:
            errors.append(f"label leakage in {contract.get('case_id')}: {', '.join(leakage[:4])}")
    return {
        "ok": not errors,
        "state": manifest.get("state"),
        "dataset_dir": str(root),
        "dataset": manifest.get("name"),
        "case_count": len(contracts),
        "dataset_sha256": expected_hashes.get("dataset_sha256"),
        "labels_separated": True,
        "errors": errors,
        "manifest": manifest,
    }


def copy_blind_inputs(dataset_dir: str | Path, destination: str | Path) -> dict[str, Any]:
    """Export only benchmark inputs/provenance for a blind execution environment."""
    verification = verify_dataset(dataset_dir)
    if not verification["ok"]:
        raise ValueError("dataset verification failed: " + "; ".join(verification["errors"]))
    src = Path(dataset_dir)
    dst = Path(destination)
    if dst.exists():
        raise FileExistsError(f"destination exists: {dst}")
    dst.mkdir(parents=True)
    manifest = verification["manifest"]
    for name in (manifest["files"]["contracts"], manifest["files"]["provenance"], manifest["files"]["evidence"]):
        shutil.copy2(src / name, dst / name)
    blind_manifest = {
        "schema": manifest["schema"],
        "name": manifest["name"],
        "state": "BLIND_INPUT_EXPORT",
        "case_count": manifest["case_count"],
        "dataset_sha256": manifest["hashes"]["dataset_sha256"],
        "contracts_sha256": manifest["hashes"]["contracts_sha256"],
        "provenance_sha256": manifest["hashes"]["provenance_sha256"],
        "evidence_sha256": manifest["hashes"]["evidence_sha256"],
        "labels_included": False,
    }
    (dst / "blind_manifest.json").write_text(json.dumps(blind_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return blind_manifest
