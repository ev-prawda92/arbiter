"""Arbiter v0.34 decision-operations helpers.

This module connects a governed DecisionRecord to operational follow-through without
pretending that a human workflow action is itself a binding market resolution.
It prepares cluster actions, records reevaluation intent, updates work ownership/state,
and computes before/after workload compression metrics.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


BLOCKER_TO_DECISION_TYPE = {
    "authority_conflict": "authority_precedence",
    "evidence_conflict": "evidence_sufficiency",
    "evidence_review": "evidence_sufficiency",
    "timing_revision": "timing_revision",
    "policy_interpretation": "policy_interpretation",
    "operator_review": "operator_approval",
    "resolution_hold": "other",
    "audit_integrity": "other",
    "evidence_missing": "other",
    "monitoring": "other",
}


@dataclass(frozen=True)
class DecisionApplication:
    decision_id: str
    cluster_id: str | None
    affected_case_ids: list[str]
    updated_case_ids: list[str]
    skipped_case_ids: list[str]
    reevaluation_requested: bool
    boundary: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "cluster_id": self.cluster_id,
            "affected_case_ids": self.affected_case_ids,
            "updated_case_ids": self.updated_case_ids,
            "skipped_case_ids": self.skipped_case_ids,
            "reevaluation_requested": self.reevaluation_requested,
            "boundary": self.boundary,
        }


def decision_type_for_blocker(blocker_type: str | None) -> str:
    return BLOCKER_TO_DECISION_TYPE.get(str(blocker_type or "").strip().lower(), "other")


def build_decision_prompt(cluster: dict[str, Any], selected_case: dict[str, Any] | None = None) -> dict[str, Any]:
    """Create the smallest explicit human judgment represented by a work pattern."""
    blocker = str(cluster.get("blocker_type") or "operator_review")
    action = cluster.get("primary_action") or cluster.get("recommended_action") or "Review governed decision"
    root = cluster.get("root_cause") or (selected_case or {}).get("detail") or "A governed exception remains unresolved."
    clear = cluster.get("clear_condition") or "Record the controlling judgment, then re-evaluate affected cases."
    questions = {
        "authority_conflict": "Which governed authority controls for this work pattern?",
        "evidence_conflict": "Which governed evidence is sufficient and controlling for this work pattern?",
        "evidence_review": "Does the available evidence satisfy the governed contract requirements?",
        "timing_revision": "Which observation window or revision controls under the governing rules?",
        "policy_interpretation": "What governed policy interpretation should control this work pattern?",
        "operator_review": "Should the governed resolution advance through the required human review step?",
        "resolution_hold": "Which blocking prerequisite must be cleared before this work pattern can advance?",
        "audit_integrity": "Is audit integrity restored sufficiently for settlement-sensitive work to continue?",
        "evidence_missing": "Is there any safe human action now, or must this remain waiting for external evidence?",
    }
    return {
        "decision_type": decision_type_for_blocker(blocker),
        "question": questions.get(blocker, f"What governed judgment resolves this {blocker.replace('_', ' ')} pattern?"),
        "recommended_action": action,
        "context": root,
        "clear_condition": clear,
        "affected_case_ids": list(cluster.get("case_ids") or []),
        "cluster_id": cluster.get("cluster_id"),
    }


def apply_decision_to_workflow(
    *,
    resolution_store,
    decision: dict[str, Any],
    current_queue: dict[str, Any],
    actor: str,
    owner: str = "Resolution Ops",
) -> dict[str, Any]:
    """Attach a decision to affected work and request reevaluation.

    This updates only workflow state. It never mutates contract semantics, evidence,
    deterministic resolution outcome, settlement authorization, or payout state.
    """
    # A superseded decision is no longer authoritative and must not be applied.
    decision_id = str(decision.get("decision_id") or "")
    if decision_id:
        from .decision_records import DecisionRecordService
        if DecisionRecordService(resolution_store).is_superseded(decision_id):
            raise ValueError(f"refusing to apply superseded decision {decision_id}")
    by_id = {str(item.get("id")): item for item in (current_queue.get("items") or [])}
    affected = [str(x) for x in (decision.get("affected_case_ids") or []) if x]
    updated: list[str] = []
    skipped: list[str] = []
    note = f"Governed decision {decision.get('decision_id')} recorded; reevaluation requested."
    for case_id in affected:
        item = by_id.get(case_id)
        if not item or str(item.get("status") or "open") == "resolved":
            skipped.append(case_id)
            continue
        resolution_store.set_work_state(case_id, "in_progress", owner, note, actor)
        updated.append(case_id)

    application = DecisionApplication(
        decision_id=str(decision.get("decision_id")),
        cluster_id=decision.get("cluster_id"),
        affected_case_ids=affected,
        updated_case_ids=updated,
        skipped_case_ids=skipped,
        reevaluation_requested=bool(updated),
        boundary=(
            "Decision application changes workflow state and requests governed reevaluation only. "
            "It does not directly change contract terms, evidence, YES/NO/HOLD outcomes, or settlement authorization."
        ),
    )
    resolution_store._audit(
        actor,
        "decision.reevaluation.requested",
        "decision_record",
        str(decision.get("decision_id")),
        application.to_dict(),
    )
    return application.to_dict()


def _ops_summary(overview: dict[str, Any] | None) -> dict[str, Any]:
    return (((overview or {}).get("agent_brief") or {}).get("operations_intelligence") or {}).get("summary") or {}


def workload_snapshot(overview: dict[str, Any] | None) -> dict[str, Any]:
    s = _ops_summary(overview)
    active = int(s.get("active_cases") or 0)
    decisions = int(s.get("estimated_human_decisions") or 0)
    waits = int(s.get("waiting_on_external_data") or 0)
    return {
        "active_cases": active,
        "human_decisions": decisions,
        "waiting_external": waits,
        "human_decisions_avoided": int(s.get("human_decisions_avoided") or max(0, active - decisions)),
        "distinct_work_patterns": int(s.get("distinct_work_patterns") or 0),
        "compression_ratio": float(s.get("compression_ratio") or 1.0),
        "notional_represented": float(s.get("notional_represented") or 0),
    }


def workload_delta(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    keys = ("active_cases", "human_decisions", "waiting_external", "human_decisions_avoided", "distinct_work_patterns")
    return {
        "before": dict(before),
        "after": dict(after),
        "delta": {k: int(after.get(k, 0)) - int(before.get(k, 0)) for k in keys},
        "cases_cleared": max(0, int(before.get("active_cases", 0)) - int(after.get("active_cases", 0))),
        "human_decisions_removed": max(0, int(before.get("human_decisions", 0)) - int(after.get("human_decisions", 0))),
        "boundary": "These are workflow-compression metrics; they are not claims of binding settlement or financial accuracy.",
    }


def reevaluate(
    *,
    workflow_builder: Callable[[], tuple],
    before_overview: dict[str, Any],
) -> dict[str, Any]:
    """Regenerate the governed queue and compare operator workload before/after."""
    before = workload_snapshot(before_overview)
    payload = workflow_builder()
    queue = payload[3]
    overview = payload[-1]
    after = workload_snapshot(overview)
    return {
        "queue": queue,
        "overview": overview,
        "workload": workload_delta(before, after),
    }


# ---------------------------------------------------------------------------
# v0.35: authoritative decisions clear the work they answer
# ---------------------------------------------------------------------------

# Blockers that exist only because a human judgment was missing. A recorded,
# authoritative decision supplies that judgment, so the work item's required
# action is complete.
DECIDABLE_BLOCKERS = {
    "timing_revision",
    "policy_interpretation",
    "authority_conflict",
    "evidence_conflict",
    "evidence_review",
}

# Work that reflects live state of the world. A decision can never clear it:
# a payout HOLD, a suspended/monitored source, a broken audit chain, or
# evidence that has not arrived.
NEVER_CLEARED_KINDS = {
    "resolution_hold",
    "authority_status",
    "audit_integrity",
    "evidence_gap",
}


def apply_authoritative_decisions(
    queue: dict[str, Any],
    decisions: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return a copy of ``queue`` with decision-answered work marked resolved.

    Pure and derived: nothing is persisted. The queue is rebuilt from governed
    state on every request, so superseding or withdrawing a decision simply
    stops it from appearing in ``decisions`` and the work reopens.

    A work item is cleared only when ALL hold:
      * its id is in the decision's recorded ``affected_case_ids``;
      * it still belongs to the decision's work pattern (same cluster id now
        as when the decision was recorded), so drifted work is not cleared;
      * its blocker is a judgment blocker, and its kind is not live-state work;
      * an operator has not explicitly reopened it after the decision.

    This changes workflow status only. It never touches contract terms,
    evidence, YES/NO/HOLD outcomes, settlement, or payout authorization.
    """
    from .operations_intelligence import _blocker, _cluster_signature, _stable_cluster_id

    by_case: dict[str, dict[str, Any]] = {}
    # Oldest first so the most recent authoritative decision wins on overlap.
    for d in sorted(decisions, key=lambda r: str(r.get("created_at") or "")):
        if str(d.get("state") or "recorded") != "recorded":
            continue
        for case_id in d.get("affected_case_ids") or []:
            by_case[str(case_id)] = d

    items: list[dict[str, Any]] = []
    cleared: list[str] = []
    for raw in queue.get("items") or []:
        item = dict(raw)
        decision = by_case.get(str(item.get("id")))
        if decision and item.get("status") != "resolved":
            blocker = _blocker(item)
            cluster_now = _stable_cluster_id(blocker, _cluster_signature(item))
            reopened_after = (
                item.get("status") == "open"
                and item.get("updated_at")
                and str(item["updated_at"]) > str(decision.get("created_at") or "")
            )
            if (
                blocker in DECIDABLE_BLOCKERS
                and str(item.get("kind") or "") not in NEVER_CLEARED_KINDS
                and cluster_now == decision.get("cluster_id")
                and not reopened_after
            ):
                item["status"] = "resolved"
                item["note"] = (
                    f"Cleared by governed decision {decision.get('decision_id')}: "
                    f"{decision.get('selection')}"
                )
                item["governed_by"] = {
                    "decision_id": decision.get("decision_id"),
                    "decision_hash": decision.get("decision_hash"),
                    "decision_type": decision.get("decision_type"),
                    "selection": decision.get("selection"),
                    "cluster_id": decision.get("cluster_id"),
                }
                cleared.append(str(item.get("id")))
        items.append(item)

    order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    status_order = {"open": 0, "in_progress": 1, "resolved": 2}
    items.sort(key=lambda x: (status_order.get(x.get("status"), 0), order.get(x.get("severity"), 9), -float(x.get("notional") or 0)))
    active = [i for i in items if i.get("status") != "resolved"]
    summary = {
        "active": len(active),
        "critical": sum(i.get("severity") == "critical" for i in active),
        "high": sum(i.get("severity") == "high" for i in active),
        "in_progress": sum(i.get("status") == "in_progress" for i in active),
        "notional": sum(float(i.get("notional") or 0) for i in active),
        "cleared_by_decision": len(cleared),
    }
    return {**queue, "items": items, "summary": summary, "cleared_by_decision": cleared}
