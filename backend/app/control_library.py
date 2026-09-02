"""Arbiter resolution control library v0.1.

Controls are technical governance checks, not claims of legal compliance.
Exchanges remain responsible for their own rules and regulatory obligations.
"""
from __future__ import annotations
from typing import Any

CONTROLS = [
    {"id": "RES-001", "severity": "block", "name": "Approved authority required", "description": "Every contract must designate at least one governed resolution authority."},
    {"id": "RES-002", "severity": "block", "name": "Settlement timing defined", "description": "The resolution observation or settlement window must be machine-identifiable."},
    {"id": "RES-003", "severity": "block", "name": "Objective definition required", "description": "The contract must define an objectively evaluable event, value, threshold, or official declaration."},
    {"id": "RES-004", "severity": "block", "name": "Source precedence required", "description": "Contracts with multiple authorities must define precedence or fallback behavior."},
    {"id": "RES-005", "severity": "review", "name": "Revision policy required when applicable", "description": "Revision-prone evidence must identify which publication or revision cutoff controls."},
    {"id": "RES-006", "severity": "block", "name": "Evidence provenance required", "description": "Settlement evidence must retain authority version, retrieval time, raw payload hash, and parser version."},
    {"id": "RES-007", "severity": "block", "name": "Version-pinned resolution run", "description": "Every run must pin contract, policy, engine, and evidence versions."},
    {"id": "RES-008", "severity": "review", "name": "Exceptions require governed disposition", "description": "A resolution run with exceptions cannot silently settle without an explicit governed disposition."},
]


def evaluate_spec(spec: dict[str, Any], known_authorities: set[str]) -> list[dict[str, Any]]:
    results = []
    authority_ids = spec.get("authority_ids") or []
    definition = spec.get("definition") or {}
    timing = spec.get("timing") or {}
    source_precedence = spec.get("source_precedence") or []
    revision_policy = spec.get("revision_policy") or {}
    checks = {
        "RES-001": bool(authority_ids) and all(a in known_authorities for a in authority_ids),
        "RES-002": bool(timing),
        "RES-003": bool(definition),
        "RES-004": len(authority_ids) <= 1 or bool(source_precedence),
        "RES-005": bool(revision_policy) or not spec.get("metadata", {}).get("revision_prone", False),
    }
    for control in CONTROLS[:5]:
        passed = checks[control["id"]]
        results.append({**control, "passed": passed, "status": "PASS" if passed else ("BLOCK" if control["severity"] == "block" else "REVIEW")})
    return results


def evaluate_evidence(record: dict[str, Any]) -> list[dict[str, Any]]:
    required = ["authority_id", "authority_version", "retrieved_at", "raw_payload_hash", "parser_version", "record_hash"]
    passed = all(record.get(k) not in (None, "") for k in required)
    c = next(c for c in CONTROLS if c["id"] == "RES-006")
    return [{**c, "passed": passed, "status": "PASS" if passed else "BLOCK"}]


def evaluate_run(run: dict[str, Any]) -> list[dict[str, Any]]:
    pinned = all(run.get(k) not in (None, "", []) for k in ("contract_id", "contract_version", "policy_version", "engine_version"))
    exceptions_ok = not run.get("exceptions") or bool(run.get("approvals")) or run.get("outcome") in ("HOLD", "PENDING")
    out = []
    for cid, passed in (("RES-007", pinned), ("RES-008", exceptions_ok)):
        c = next(c for c in CONTROLS if c["id"] == cid)
        out.append({**c, "passed": passed, "status": "PASS" if passed else ("BLOCK" if c["severity"] == "block" else "REVIEW")})
    return out
