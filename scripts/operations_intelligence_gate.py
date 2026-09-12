#!/usr/bin/env python3
"""Deterministic gate for Arbiter Operations Intelligence v0.31."""
from backend.app.operations_intelligence import analyze_queue


def check(condition, label):
    if not condition:
        raise AssertionError(label)
    print(f"[PASS] {label}")


def main():
    queue = {
        "items": [
            {
                "id": "w1", "kind": "evidence_conflict", "title": "Conflicting governed evidence: AUTH-X-a1",
                "detail": "AUTH-X-a1 produced a value that differs from another governed authority.",
                "severity": "critical", "status": "open", "owner_role": "Resolution Ops",
                "recommended_action": "Review source precedence before settlement.", "notional": 4_000_000,
            },
            {
                "id": "w2", "kind": "evidence_conflict", "title": "Conflicting governed evidence: AUTH-X-b2",
                "detail": "AUTH-X-b2 produced a value that differs from another governed authority.",
                "severity": "high", "status": "open", "owner_role": "Resolution Ops",
                "recommended_action": "Review source precedence before settlement.", "notional": 2_000_000,
            },
            {
                "id": "w3", "kind": "evidence_gap", "title": "Official report not yet available",
                "detail": "Waiting on external data from the approved source publication.",
                "severity": "high", "status": "open", "owner_role": "Data Ops",
                "recommended_action": "Wait for authoritative evidence before settlement.", "notional": 1_000_000,
            },
            {
                "id": "w4", "kind": "policy_review", "title": "Definition ambiguity requires policy review",
                "detail": "Contract definition is ambiguous and requires policy interpretation.",
                "severity": "high", "status": "open", "owner_role": "Compliance",
                "recommended_action": "Review governing definition.", "notional": 0,
            },
            {
                "id": "w5", "kind": "monitoring", "title": "Monitor source risk",
                "detail": "Monitor source publication before resolution window closes.",
                "severity": "medium", "status": "resolved", "owner_role": "Market Ops",
                "recommended_action": "Continue monitoring.", "notional": 0,
            },
        ]
    }

    result = analyze_queue(queue)
    summary = result["summary"]

    check(result["mode"] == "advisory_non_binding", "operations intelligence stays advisory")
    check(summary["active_cases"] == 4, "resolved work excluded from active analysis")
    check(summary["waiting_on_external_data"] == 1, "external evidence wait detected")
    check(summary["policy_interpretation"] == 1, "policy interpretation detected")
    check(summary["distinct_work_patterns"] < summary["active_cases"], "repeated work compressed into fewer patterns")
    check(any(c["count"] == 2 for c in result["clusters"]), "duplicate evidence-conflict pattern clustered")
    check(result["recommended_sequence"], "recommended work sequence produced")
    check(result["ready_cases"], "ready-for-review cases surfaced")

    print("OPERATIONS INTELLIGENCE GATE: PASS")


if __name__ == "__main__":
    main()
