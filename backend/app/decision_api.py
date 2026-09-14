"""FastAPI router for Arbiter v0.34 governed Decision Records.

The router is dependency-injected so the existing main application can mount it with
one include_router call while keeping DecisionRecord storage and reevaluation logic
independently testable.
"""
from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from . import decision_operations, decision_records


class DecisionCreateIn(BaseModel):
    cluster_id: str
    selection: str
    rationale: str
    governing_rule: str = ""
    controlling_authority_ids: list[str] = Field(default_factory=list)
    controlling_evidence_ids: list[str] = Field(default_factory=list)
    policy_basis: dict[str, Any] = Field(default_factory=dict)
    precedent_ids: list[str] = Field(default_factory=list)
    owner: str = "Resolution Ops"
    actor: str = "operator:resolution-ops"


class DecisionPrecedentQuery(BaseModel):
    decision_type: str
    governing_rule: str = ""
    exclude_cluster_id: str | None = None
    limit: int = 5


def _cluster_from_overview(overview: dict[str, Any], cluster_id: str) -> dict[str, Any] | None:
    ops = ((overview.get("agent_brief") or {}).get("operations_intelligence") or {})
    return next((c for c in (ops.get("clusters") or []) if c.get("cluster_id") == cluster_id), None)


def build_router(
    *,
    resolution_store,
    workflow_builder: Callable[[], tuple],
    require_scope: Callable[[str], Any],
) -> APIRouter:
    router = APIRouter(tags=["Decision Operations"])

    @router.get("/api/decisions")
    def list_decisions(
        cluster_id: str | None = None,
        contract_id: str | None = None,
        decision_type: str | None = None,
        limit: int = 100,
    ):
        svc = decision_records.get_service(resolution_store)
        return {
            "decisions": svc.list(
                cluster_id=cluster_id,
                contract_id=contract_id,
                decision_type=decision_type,
                limit=limit,
            ),
            "posture": svc.posture(),
        }

    @router.get("/api/decisions/{decision_id}")
    def get_decision(decision_id: str):
        record = decision_records.get_service(resolution_store).get(decision_id)
        if not record:
            raise HTTPException(404, "decision not found")
        return {"decision": record}

    @router.get("/api/decision-context/{cluster_id}")
    def decision_context(cluster_id: str):
        payload = workflow_builder()
        queue, overview = payload[3], payload[-1]
        cluster = _cluster_from_overview(overview, cluster_id)
        if not cluster:
            raise HTTPException(404, "work pattern not found")
        active = [i for i in (queue.get("items") or []) if i.get("status") != "resolved"]
        case_ids = set(cluster.get("case_ids") or [])
        selected = next((i for i in active if i.get("id") in case_ids), None)
        prompt = decision_operations.build_decision_prompt(cluster, selected)
        precedents = decision_records.get_service(resolution_store).related_precedents(
            decision_type=prompt["decision_type"],
            governing_rule="",
            exclude_cluster_id=cluster_id,
            limit=5,
        )
        return {
            "cluster": cluster,
            "decision_prompt": prompt,
            "precedents": precedents,
            "workload": decision_operations.workload_snapshot(overview),
            "boundary": "This endpoint prepares a human judgment; it does not change a governed outcome.",
        }

    @router.post("/api/decision-precedents")
    def decision_precedents(inp: DecisionPrecedentQuery):
        svc = decision_records.get_service(resolution_store)
        return {
            "precedents": svc.related_precedents(
                decision_type=inp.decision_type,
                governing_rule=inp.governing_rule,
                exclude_cluster_id=inp.exclude_cluster_id,
                limit=inp.limit,
            )
        }

    @router.post("/api/decisions")
    def create_decision(
        inp: DecisionCreateIn,
        auth=Depends(require_scope("operations:write")),
    ):
        before_payload = workflow_builder()
        before_queue, before_overview = before_payload[3], before_payload[-1]
        cluster = _cluster_from_overview(before_overview, inp.cluster_id)
        if not cluster:
            raise HTTPException(404, "work pattern not found")

        active_by_id = {
            str(i.get("id")): i
            for i in (before_queue.get("items") or [])
            if i.get("status") != "resolved"
        }
        affected = [str(x) for x in (cluster.get("case_ids") or []) if str(x) in active_by_id]
        selected = active_by_id.get(affected[0]) if affected else None
        prompt = decision_operations.build_decision_prompt(cluster, selected)

        if not inp.selection.strip():
            raise HTTPException(422, "selection is required")
        if not inp.rationale.strip():
            raise HTTPException(422, "rationale is required")

        svc = decision_records.get_service(resolution_store)
        try:
            record = svc.create(
                decision_type=prompt["decision_type"],
                question=prompt["question"],
                selection=inp.selection,
                rationale=inp.rationale,
                actor=inp.actor,
                affected_case_ids=affected,
                cluster_id=inp.cluster_id,
                contract_id=(selected or {}).get("subject"),
                governing_rule=inp.governing_rule,
                controlling_authority_ids=inp.controlling_authority_ids,
                controlling_evidence_ids=inp.controlling_evidence_ids,
                policy_basis=inp.policy_basis,
                precedent_ids=inp.precedent_ids,
                metadata={
                    "blocker_type": cluster.get("blocker_type"),
                    "root_cause": cluster.get("root_cause"),
                    "clear_condition": cluster.get("clear_condition"),
                    "operator_boundary": "workflow judgment only; no direct settlement mutation",
                },
            )
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

        application = decision_operations.apply_decision_to_workflow(
            resolution_store=resolution_store,
            decision=record,
            current_queue=before_queue,
            actor=inp.actor,
            owner=inp.owner,
        )
        reevaluation = decision_operations.reevaluate(
            workflow_builder=workflow_builder,
            before_overview=before_overview,
        )
        return {
            "decision": record,
            "application": application,
            "reevaluation": reevaluation,
            "precedents": svc.related_precedents(
                decision_type=record["decision_type"],
                governing_rule=record.get("governing_rule") or "",
                exclude_cluster_id=record.get("cluster_id"),
                limit=5,
            ),
            "boundary": (
                "Recording a decision may move operator workflow and request reevaluation. "
                "The deterministic resolution core remains authoritative for any YES/NO/HOLD outcome."
            ),
        }

    return router
