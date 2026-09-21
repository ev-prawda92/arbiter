#!/usr/bin/env python3
"""Release gate for Arbiter v0.34 governed decision PROPAGATION.

Proves the north-star behavior end to end:
  many unresolved cases -> a few shared human-decision boundaries ->
  record each governed decision once -> re-evaluate dependent cases ->
  safely clear everything derivable from those decisions, and NOTHING else.

Properties asserted (fail-closed):
  P1 only cases dependent on a decision are reconsidered
  P2 unrelated cases remain unchanged
  P3 resolved/final cases are not silently rewritten
  P4 decision application mutates workflow state only -- never contract,
     evidence, YES/NO/HOLD, settlement, or payout (audit-action allowlist)
  P5 superseded decisions are derivably non-authoritative
  P6 every downstream state transition has hash-chained audit provenance
  P7 replay/retry is idempotent
  P8 duplicate application does not create divergent workflow state
  P9 store contract/evidence/resolution counts are unchanged by application
"""
from __future__ import annotations

import os
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND = os.path.join(ROOT, "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from app.decision_records import get_service  # noqa: E402
from app.decision_operations import apply_decision_to_workflow  # noqa: E402
from app.resolution_infra import ResolutionStore  # noqa: E402

# Application mutates workflow state and records a re-evaluation request only.
ALLOWED_AUDIT_ACTIONS = {
    "decision.recorded",
    "work_item.updated",
    "decision.reevaluation.requested",
}
# Anything touching these object types during application would be a boundary breach.
FORBIDDEN_AUDIT_OBJECTS = {"contract", "authority", "evidence", "resolution_run", "settlement", "payout"}


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)



def main() -> None:
    with tempfile.TemporaryDirectory(prefix="arbiter-v034-prop-") as tmp:
        store = ResolutionStore(os.path.join(tmp, "arbiter.db"))
        svc = get_service(store)

        # --- scenario: a queue with dependent-open, dependent-resolved, and unrelated cases ---
        dep_open = [f"case_dep_open_{i}" for i in range(6)]
        dep_resolved = "case_dep_resolved"
        unrelated = [f"case_unrelated_{i}" for i in range(8)]
        queue = {"items": (
            [{"id": c, "status": "open"} for c in dep_open]
            + [{"id": dep_resolved, "status": "resolved"}]
            + [{"id": c, "status": "open"} for c in unrelated]
        )}

        before = store.summary()

        decision = svc.create(
            decision_type="authority_precedence",
            question="Which governed authority controls this work pattern?",
            selection="initial_official_release",
            rationale="The governing rule pins the initial official release; later revisions do not supersede.",
            actor="operator:resolution-ops",
            affected_case_ids=dep_open + [dep_resolved],  # deliberately includes the resolved one
            cluster_id="cluster_alpha",
            contract_id="contract_alpha",
            governing_rule="Initial official release controls.",
            controlling_authority_ids=["auth_primary"],
            controlling_evidence_ids=["evid_initial"],
            policy_basis={"policy_version": "4.2"},
        )

        app1 = apply_decision_to_workflow(
            resolution_store=store, decision=decision, current_queue=queue, actor="operator:resolution-ops",
        )

        ws = store.list_work_states()

        # P1 only dependent-open cases were reconsidered
        check(set(app1["updated_case_ids"]) == set(dep_open), f"P1: updated set wrong: {app1['updated_case_ids']}")
        check(set(ws.keys()) == set(dep_open), f"P1: work-state touched non-dependent cases: {sorted(ws)}")
        check(all(ws[c]["status"] == "in_progress" for c in dep_open), "P1: dependent-open not moved to in_progress")

        # P2 unrelated cases untouched
        check(not (set(unrelated) & set(ws.keys())), "P2: an unrelated case got a work-state change")

        # P3 resolved/final case skipped, not rewritten
        check(dep_resolved in app1["skipped_case_ids"], "P3: resolved case not skipped")
        check(dep_resolved not in ws, "P3: resolved case was rewritten into work-state")
        q_status = {i["id"]: i["status"] for i in queue["items"]}
        check(q_status[dep_resolved] == "resolved", "P3: resolved case status mutated in queue")

        # P4 workflow-only: no forbidden audit actions/objects
        audit = store.audit_log(limit=1000)
        actions = {e.get("action") for e in audit}
        objects = {e.get("object_type") for e in audit}
        check(actions <= ALLOWED_AUDIT_ACTIONS, f"P4: unexpected audit action(s): {actions - ALLOWED_AUDIT_ACTIONS}")
        check(not (objects & FORBIDDEN_AUDIT_OBJECTS), f"P4: application touched forbidden object(s): {objects & FORBIDDEN_AUDIT_OBJECTS}")
        check("boundary" in app1 and "settlement" in app1["boundary"].lower(), "P4: application dropped its boundary statement")

        # P9 store semantic counts unchanged (only workflow + audit grew)
        after = store.summary()
        for k in ("contracts", "authorities", "evidence_records", "resolution_runs"):
            check(after[k] == before[k], f"P9: application changed {k} count ({before[k]} -> {after[k]})")
        check(after["work_item_states"] == len(dep_open), "P9: unexpected work_item_state count")

        # P6 audit provenance for every transition
        for c in dep_open:
            evts = store.audit_log(limit=50, object_type="work_item", object_id=c)
            check(evts, f"P6: no audit event for updated case {c}")
        reeval = [e for e in audit if e.get("action") == "decision.reevaluation.requested"]
        check(len(reeval) == 1, "P6: missing/duplicate reevaluation-requested audit event")
        check(store.verify_audit_chain().get("ok") is True, "P6: hash-chained audit invalid after propagation")

        # P7 / P8 idempotent replay -> no divergent state
        app2 = apply_decision_to_workflow(
            resolution_store=store, decision=decision, current_queue=queue, actor="operator:resolution-ops",
        )
        check(set(app2["updated_case_ids"]) == set(dep_open), "P7: replay changed the updated set")
        check(set(app2["skipped_case_ids"]) == {dep_resolved}, "P7: replay changed the skipped set")
        ws2 = store.list_work_states()
        check(set(ws2.keys()) == set(dep_open), "P8: replay created divergent work-item rows")
        check(len(ws2) == len(dep_open), f"P8: work-item row count diverged on replay: {len(ws2)}")
        check(all(ws2[c]["status"] == "in_progress" for c in dep_open), "P8: replay left a case in a divergent state")
        check(store.verify_audit_chain().get("ok") is True, "P7: audit chain invalid after replay")

        # P5 superseded decisions derivably non-authoritative
        superseding = svc.create(
            decision_type="authority_precedence",
            question="Which governed authority controls this work pattern?",
            selection="revised_official_release",
            rationale="A later governed policy clarification changed the applicable revision rule.",
            actor="operator:resolution-ops",
            affected_case_ids=dep_open,
            cluster_id="cluster_beta",
            contract_id="contract_alpha",
            governing_rule="Latest valid official revision controls.",
            policy_basis={"policy_version": "4.3"},
            supersedes=decision["decision_id"],
        )
        auth_ids = {r["decision_id"] for r in svc.authoritative()}
        check(decision["decision_id"] not in auth_ids, "P5: superseded decision still authoritative in data")
        check(superseding["decision_id"] in auth_ids, "P5: superseding decision not authoritative")
        try:
            apply_decision_to_workflow(
                resolution_store=store, decision=decision, current_queue=queue, actor="operator:resolution-ops",
            )
        except ValueError:
            pass
        else:
            raise AssertionError("P5: superseded decision was applied instead of refused at apply time")

        print("DECISION PROPAGATION GATE: PASS")
        print(f"{len(dep_open)} dependent cleared · 1 resolved skipped · {len(unrelated)} unrelated untouched · "
              f"idempotent replay · workflow-only boundary held · hash-chained audit intact")
        print("P5 enforced: superseded decisions are excluded from svc.authoritative() AND refused by "
              "apply_decision_to_workflow() at apply time.")


if __name__ == "__main__":
    main()
