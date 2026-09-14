#!/usr/bin/env python3
"""Release gate for Arbiter v0.34 governed decision records."""
from __future__ import annotations

import os
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND = os.path.join(ROOT, "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from app.decision_records import get_service  # noqa: E402
from app.resolution_infra import ResolutionStore  # noqa: E402


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="arbiter-v034-") as tmp:
        store = ResolutionStore(os.path.join(tmp, "arbiter.db"))
        svc = get_service(store)

        first = svc.create(
            decision_type="authority_precedence",
            question="Which publication controls this resolution?",
            selection="initial_official_release",
            rationale="The governing rule explicitly pins the initial official release.",
            actor="operator:resolution-ops",
            affected_case_ids=["case_1", "case_2", "case_3"],
            cluster_id="cluster_demo",
            contract_id="contract_demo",
            governing_rule="Initial official release controls; later revisions do not supersede.",
            controlling_authority_ids=["auth_primary"],
            controlling_evidence_ids=["evid_initial"],
            policy_basis={"policy_version": "4.2"},
        )
        check(first["schema"] == "arbiter.decision-record.v1", "schema mismatch")
        check(first["decision_hash"].startswith("sha256:"), "decision hash missing")
        check(svc.get(first["decision_id"])["selection"] == "initial_official_release", "round-trip failed")

        related = svc.related_precedents(
            decision_type="authority_precedence",
            governing_rule="Initial official release controls; later revisions do not supersede.",
            exclude_cluster_id="different_cluster",
        )
        check(related and related[0]["decision_id"] == first["decision_id"], "precedent retrieval failed")

        second = svc.create(
            decision_type="authority_precedence",
            question="Which publication controls this resolution?",
            selection="revised_official_release",
            rationale="A later governed policy clarification changed the applicable revision rule.",
            actor="operator:resolution-ops",
            affected_case_ids=["case_4"],
            cluster_id="cluster_demo_2",
            contract_id="contract_demo",
            governing_rule="Latest valid official revision controls.",
            controlling_authority_ids=["auth_primary"],
            controlling_evidence_ids=["evid_revision"],
            policy_basis={"policy_version": "4.3"},
            supersedes=first["decision_id"],
        )
        check(second["supersedes"] == first["decision_id"], "supersession link failed")

        records = svc.list(contract_id="contract_demo")
        check(len(records) == 2, "contract decision history incomplete")

        posture = svc.posture()
        check(posture["count"] == 2, "posture count mismatch")

        audit = store.verify_audit_chain()
        check(audit.get("valid") is True, "audit chain failed after decisions")

        try:
            svc.create(
                decision_type="unsupported",
                question="Bad decision",
                selection="x",
                rationale="x",
                actor="operator:test",
                affected_case_ids=["case_bad"],
            )
        except ValueError:
            pass
        else:
            raise AssertionError("unsupported decision type did not fail closed")

        print("DECISION RECORD GATE: PASS")
        print("2 durable decisions · hash chained audit · deterministic precedent candidates · fail-closed validation")


if __name__ == "__main__":
    main()
