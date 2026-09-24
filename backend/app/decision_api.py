"""FastAPI router for Arbiter v0.34 governed Decision Records.

The router is dependency-injected so the existing main application can mount it with
one include_router call while keeping DecisionRecord storage and reevaluation logic
independently testable.
"""

from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from . import decision_operations, decision_records, precedents


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
    # Departing from an applicable precedent needs one of these (v0.39).
    distinguish: str = ""
    overrules: str | None = None


class AppealCheckIn(BaseModel):
    contract_id: str
    requested_selection: str
    grounds: str = ""
    actor: str = "operator:resolution-ops"


class AskIn(BaseModel):
    question: str
    contract_id: str | None = None


class ConsistencyPreviewIn(BaseModel):
    cluster_id: str
    selection: str
    precedent_ids: list[str] = Field(default_factory=list)


class DecisionPrecedentQuery(BaseModel):
    decision_type: str
    governing_rule: str = ""
    exclude_cluster_id: str | None = None
    limit: int = 5


def _cluster_from_overview(overview: dict[str, Any], cluster_id: str) -> dict[str, Any] | None:
    ops = (overview.get("agent_brief") or {}).get("operations_intelligence") or {}
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
        related = decision_records.get_service(resolution_store).related_precedents(
            decision_type=prompt["decision_type"],
            governing_rule="",
            exclude_cluster_id=cluster_id,
            limit=5,
        )
        engine = precedents.get_engine(resolution_store)
        case_ids = [c for c in (cluster.get("case_ids") or []) if c in {i.get("id") for i in active}]
        applicable = engine.applicable(engine.rows_for_cases(case_ids), decision_type=prompt["decision_type"])
        return {
            "cluster": cluster,
            "clearability": decision_operations.clearability(cluster, queue.get("items") or []),
            "decision_prompt": prompt,
            "precedent_matches": applicable[:5],
            "precedents": related,
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

        active_by_id = {str(i.get("id")): i for i in (before_queue.get("items") or []) if i.get("status") != "resolved"}
        affected = [str(x) for x in (cluster.get("case_ids") or []) if str(x) in active_by_id]
        selected = active_by_id.get(affected[0]) if affected else None
        prompt = decision_operations.build_decision_prompt(cluster, selected)

        if not inp.selection.strip():
            raise HTTPException(422, "selection is required")
        if not inp.rationale.strip():
            raise HTTPException(422, "rationale is required")

        engine = precedents.get_engine(resolution_store)
        engine.refresh()  # authenticated write path: bring precedent in line with decisions
        consistency = engine.consistency(
            selection=inp.selection,
            rows=engine.rows_for_cases(affected),
            decision_type=prompt["decision_type"],
            cited=inp.precedent_ids,
        )
        top = consistency.get("precedent") or {}
        peers = consistency.get("peer_matches") or []
        # Holdings this selection departs from that an overrule would not retire.
        unanswered: list[dict[str, Any]] = []
        if inp.overrules:
            target = next((m for m in peers if m["precedent_id"] == inp.overrules), None)
            if not target:
                raise HTTPException(422, "overrules must name a precedent that applies here")
            if precedents.agrees(inp.selection, target["ruling"].get("selection") or ""):
                raise HTTPException(422, "nothing to overrule: the selection agrees with that precedent")
            holding = target["ruling"].get("selection") or ""
            unanswered = [
                m
                for m in peers
                if not precedents.agrees(holding, m["ruling"].get("selection") or "")
                and not precedents.agrees(inp.selection, m["ruling"].get("selection") or "")
            ]
            if unanswered and not inp.distinguish.strip():
                raise HTTPException(
                    409,
                    {
                        "code": "precedent_conflict",
                        "message": (
                            "The overrule retires one holding, but this also departs from "
                            + ", ".join(m["precedent_id"] for m in unanswered)
                            + ". State what distinguishes these contracts from them."
                        ),
                        "consistency": consistency,
                    },
                )
        elif consistency["status"] == "divergent" and not inp.distinguish.strip():
            raise HTTPException(
                409,
                {
                    "code": "precedent_conflict",
                    "message": (
                        f"This departs from precedent {top.get('precedent_id')}, which ruled "
                        f"\u201c{top.get('ruling', {}).get('selection')}\u201d. State what distinguishes these "
                        "contracts, or overrule the precedent."
                    ),
                    "consistency": consistency,
                },
            )

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
                precedent_ids=sorted(
                    set(inp.precedent_ids)
                    | ({top["precedent_id"]} if consistency["status"] in {"follows", "consistent"} and top else set())
                ),
                metadata={
                    "precedent_consistency": {
                        "status": consistency["status"],
                        "precedent_id": top.get("precedent_id"),
                        "tier": top.get("tier"),
                        "selection_agreement": consistency.get("selection_agreement"),
                        "distinguish": inp.distinguish.strip() or None,
                        "overrules": inp.overrules,
                    },
                    "blocker_type": cluster.get("blocker_type"),
                    "root_cause": cluster.get("root_cause"),
                    "clear_condition": cluster.get("clear_condition"),
                    "operator_boundary": "workflow judgment only; no direct settlement mutation",
                },
            )
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

        distinguished = unanswered if inp.overrules else ([top] if consistency["status"] == "divergent" else [])
        if inp.overrules:
            consistency["overruled"] = engine.overrule_line(
                inp.overrules, peers, by_decision=record["decision_id"], reason=inp.rationale, actor=inp.actor
            )
        for m in distinguished:
            resolution_store._audit(
                inp.actor,
                "precedent.distinguished",
                "precedent",
                m["precedent_id"],
                {"by_decision": record["decision_id"], "distinction": inp.distinguish.strip()},
            )
        precedent = engine.build(record)

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
            "precedent": {k: precedent.get(k) for k in ("precedent_id", "review_class", "state")}
            | {"clauses": len(precedent.get("clauses") or []), "contracts": len(precedent.get("contracts") or [])},
            "consistency": {k: v for k, v in consistency.items() if k != "applicable"},
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

    @router.post("/api/decisions/consistency")
    def consistency_preview(inp: ConsistencyPreviewIn):
        """What recording this selection would mean against precedent, before recording it."""
        payload = workflow_builder()
        queue, overview = payload[3], payload[-1]
        cluster = _cluster_from_overview(overview, inp.cluster_id)
        if not cluster:
            raise HTTPException(404, "work pattern not found")
        active = {str(i.get("id")) for i in (queue.get("items") or []) if i.get("status") != "resolved"}
        affected = [str(x) for x in (cluster.get("case_ids") or []) if str(x) in active]
        prompt = decision_operations.build_decision_prompt(cluster, None)
        engine = precedents.get_engine(resolution_store)
        return engine.consistency(
            selection=inp.selection,
            rows=engine.rows_for_cases(affected),
            decision_type=prompt["decision_type"],
            cited=inp.precedent_ids,
        )

    @router.get("/api/precedents")
    def list_precedents(include_inactive: bool = False):
        engine = precedents.get_engine(resolution_store)
        items = engine.list(include_inactive=include_inactive)
        for p in items:
            p["matched_contracts"] = len(engine.matches_for(p["precedent_id"]))
            for c in p.get("contracts") or []:
                c.pop("rules", None)
        return {"precedents": items, "posture": engine.posture()}

    @router.get("/api/precedents/match/{contract_id}")
    def match_contract(contract_id: str):
        engine = precedents.get_engine(resolution_store)
        row = engine._contract_row(contract_id)
        if not row:
            raise HTTPException(404, "contract not found")
        return {"contract_id": contract_id, "title": row.get("title"), "matches": engine.match(row, limit=5)}

    @router.get("/api/precedents/{precedent_id}")
    def get_precedent(precedent_id: str):
        engine = precedents.get_engine(resolution_store)
        p = engine.get(precedent_id)
        if not p:
            raise HTTPException(404, "precedent not found")
        return {"precedent": p, "matched_contracts": engine.matches_for(precedent_id)}

    @router.post("/api/appeals/check")
    def appeal_check(inp: AppealCheckIn, auth=Depends(require_scope("operations:write"))):
        try:
            return precedents.get_engine(resolution_store).appeal_check(
                contract_id=inp.contract_id,
                requested_selection=inp.requested_selection,
                grounds=inp.grounds,
                actor=(auth or {}).get("principal_id") or inp.actor,
            )
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc

    @router.post("/api/ask")
    def ask(inp: AskIn):
        if not inp.question.strip():
            raise HTTPException(422, "question is required")
        return precedents.get_engine(resolution_store).ask(inp.question, contract_id=inp.contract_id)

    return router
