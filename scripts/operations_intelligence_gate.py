#!/usr/bin/env python3
"""Deterministic gate for Arbiter Operations Intelligence v0.32."""

from pathlib import Path
import sys

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from backend.app.operations_intelligence import analyze_queue


def check(condition, label):
    if not condition:
        raise AssertionError(label)
    print(f"[PASS] {label}")


def main():
    queue = {
        "items": [
            {
                "id": "w1",
                "kind": "evidence_conflict",
                "title": "Conflicting governed evidence: AUTH-X-a1",
                "detail": "AUTH-X-a1 produced a value that differs from another governed authority.",
                "severity": "critical",
                "status": "open",
                "owner_role": "Resolution Ops",
                "recommended_action": "Review source precedence before settlement.",
                "notional": 4_000_000,
            },
            {
                "id": "w2",
                "kind": "evidence_conflict",
                "title": "Conflicting governed evidence: AUTH-X-b2",
                "detail": "AUTH-X-b2 produced a value that differs from another governed authority.",
                "severity": "high",
                "status": "open",
                "owner_role": "Resolution Ops",
                "recommended_action": "Review source precedence before settlement.",
                "notional": 2_000_000,
            },
            {
                "id": "w3",
                "kind": "evidence_gap",
                "title": "Official report not yet available",
                "detail": "Waiting on external data from the approved source publication.",
                "severity": "high",
                "status": "open",
                "owner_role": "Data Ops",
                "recommended_action": "Wait for authoritative evidence before settlement.",
                "notional": 1_000_000,
            },
            {
                "id": "w4",
                "kind": "policy_review",
                "title": "Definition ambiguity requires policy review",
                "detail": "Contract definition is ambiguous and requires policy interpretation.",
                "severity": "high",
                "status": "open",
                "owner_role": "Compliance",
                "recommended_action": "Review governing definition.",
                "notional": 0,
            },
            {
                "id": "w5",
                "kind": "monitoring",
                "title": "Monitor source risk",
                "detail": "Monitor source publication before resolution window closes.",
                "severity": "medium",
                "status": "resolved",
                "owner_role": "Market Ops",
                "recommended_action": "Continue monitoring.",
                "notional": 0,
            },
            {
                "id": "w6",
                "kind": "operator_review",
                "title": "Routine governed review",
                "detail": "Evidence and authority checks are complete; operator review remains.",
                "severity": "medium",
                "status": "open",
                "owner_role": "Resolution Ops",
                "recommended_action": "Confirm governed record before settlement.",
                "notional": 500_000,
                "ready_for_review": True,
            },
            {
                "id": "w7",
                "kind": "resolution_hold",
                "title": "Resolution HOLD",
                "detail": "HOLD remains while conflicting evidence is investigated.",
                "severity": "high",
                "status": "open",
                "owner_role": "Resolution Ops",
                "recommended_action": "Investigate before review.",
                "notional": 750_000,
                "resolution": "HOLD",
            },
        ]
    }

    result = analyze_queue(queue)
    summary = result["summary"]
    conflict_cluster = next(c for c in result["clusters"] if c["blocker_type"] == "evidence_conflict")

    check(result["mode"] == "advisory_non_binding", "operations intelligence stays advisory")
    check(result["version"] == "0.32.0", "v0.32 semantics are active")
    check(summary["active_cases"] == 6, "resolved work excluded from active analysis")
    check(summary["waiting_on_external_data"] == 1, "external evidence wait detected")
    check(summary["policy_interpretation"] == 1, "policy interpretation detected")
    check(summary["needs_investigation"] >= 3, "conflicts and HOLD remain investigative")
    check(summary["ready_for_review"] == 1, "ready-now metric is conservative")
    check(summary["distinct_work_patterns"] < summary["active_cases"], "repeated work compressed into fewer patterns")
    check(conflict_cluster["count"] == 2, "duplicate evidence-conflict pattern clustered")
    check(bool(conflict_cluster.get("root_cause")), "cluster exposes root cause")
    check(bool(conflict_cluster.get("why_human")), "cluster explains why human judgment remains")
    check(bool(conflict_cluster.get("clear_condition")), "cluster exposes a clear condition")
    check(conflict_cluster.get("primary_action") == "Review conflicting evidence", "cluster exposes one primary action")
    check(result["recommended_sequence"], "recommended work sequence produced")
    check(len(result["ready_cases"]) == 1, "only truly ready case surfaced")
    check(len(result["policy_cases"]) == 1, "policy-review cases are surfaced explicitly")
    check(any(i["id"] == "w7" for i in result["investigating_cases"]), "HOLD is not mislabeled ready")
    check(
        summary["estimated_human_decisions"] < summary["active_cases"], "cluster-first human decision load is reduced"
    )
    check(summary["human_decisions_avoided"] > 0, "friction-reduction metric is produced")

    print("OPERATIONS INTELLIGENCE GATE: PASS")


if __name__ == "__main__":
    main()
