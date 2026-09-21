"""Arbiter v0.34 governed decision records.

A DecisionRecord captures the irreducible human judgment that remains after Arbiter
has assembled rules, authority, evidence, timing, and precedent. Decision records
are append-only, auditable, and explicitly non-settlement-authorizing: recording a
judgment may trigger downstream re-evaluation, but it never mutates contract terms,
evidence, or a binding YES/NO/HOLD outcome by itself.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

from .resolution_infra import canonical_hash, gen_id, utcnow


DECISION_TYPES = {
    "authority_precedence",
    "evidence_sufficiency",
    "timing_revision",
    "policy_interpretation",
    "operator_approval",
    "other",
}

DECISION_STATES = {"recorded", "superseded", "withdrawn"}


@dataclass(frozen=True)
class DecisionRecord:
    decision_id: str
    decision_type: str
    question: str
    selection: str
    rationale: str
    actor: str
    affected_case_ids: list[str] = field(default_factory=list)
    cluster_id: str | None = None
    contract_id: str | None = None
    governing_rule: str = ""
    controlling_authority_ids: list[str] = field(default_factory=list)
    controlling_evidence_ids: list[str] = field(default_factory=list)
    policy_basis: dict[str, Any] = field(default_factory=dict)
    precedent_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utcnow)
    state: str = "recorded"
    supersedes: str | None = None
    schema: str = "arbiter.decision-record.v1"

    def validate(self) -> list[str]:
        errors: list[str] = []
        if self.decision_type not in DECISION_TYPES:
            errors.append(f"unsupported decision_type: {self.decision_type}")
        if not self.question.strip():
            errors.append("question is required")
        if not self.selection.strip():
            errors.append("selection is required")
        if not self.rationale.strip():
            errors.append("rationale is required")
        if not self.actor.strip():
            errors.append("actor is required")
        if self.state not in DECISION_STATES:
            errors.append(f"unsupported state: {self.state}")
        if not (self.affected_case_ids or self.cluster_id or self.contract_id):
            errors.append("decision must be bound to at least one case, cluster, or contract")
        return errors

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["decision_hash"] = canonical_hash(payload)
        return payload


class DecisionRecordService:
    """Durable append-oriented storage for governed human judgments."""

    def __init__(self, resolution_store):
        self.store = resolution_store
        self._init_db()

    def _init_db(self) -> None:
        with self.store.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS decision_records (
                    decision_id TEXT PRIMARY KEY,
                    decision_type TEXT NOT NULL,
                    cluster_id TEXT,
                    contract_id TEXT,
                    created_at TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    state TEXT NOT NULL,
                    supersedes TEXT,
                    decision_json TEXT NOT NULL,
                    decision_hash TEXT NOT NULL UNIQUE
                );
                CREATE INDEX IF NOT EXISTS ix_decision_records_cluster
                    ON decision_records(cluster_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS ix_decision_records_contract
                    ON decision_records(contract_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS ix_decision_records_type
                    ON decision_records(decision_type, created_at DESC);
                """
            )

    def create(
        self,
        *,
        decision_type: str,
        question: str,
        selection: str,
        rationale: str,
        actor: str,
        affected_case_ids: list[str] | None = None,
        cluster_id: str | None = None,
        contract_id: str | None = None,
        governing_rule: str = "",
        controlling_authority_ids: list[str] | None = None,
        controlling_evidence_ids: list[str] | None = None,
        policy_basis: dict[str, Any] | None = None,
        precedent_ids: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        supersedes: str | None = None,
    ) -> dict[str, Any]:
        record = DecisionRecord(
            decision_id=gen_id("dec"),
            decision_type=decision_type,
            question=question,
            selection=selection,
            rationale=rationale,
            actor=actor,
            affected_case_ids=list(affected_case_ids or []),
            cluster_id=cluster_id,
            contract_id=contract_id,
            governing_rule=governing_rule,
            controlling_authority_ids=list(controlling_authority_ids or []),
            controlling_evidence_ids=list(controlling_evidence_ids or []),
            policy_basis=dict(policy_basis or {}),
            precedent_ids=list(precedent_ids or []),
            metadata=dict(metadata or {}),
            supersedes=supersedes,
        )
        errors = record.validate()
        if errors:
            raise ValueError("; ".join(errors))

        if supersedes and not self.get(supersedes):
            raise ValueError("supersedes references unknown decision")

        payload = record.to_dict()
        with self.store.connect() as db:
            db.execute(
                "INSERT INTO decision_records(decision_id,decision_type,cluster_id,contract_id,created_at,actor,state,supersedes,decision_json,decision_hash) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    record.decision_id,
                    record.decision_type,
                    record.cluster_id,
                    record.contract_id,
                    record.created_at,
                    record.actor,
                    record.state,
                    record.supersedes,
                    json.dumps(payload, sort_keys=True),
                    payload["decision_hash"],
                ),
            )

        # Reuse the existing hash-chained audit log so a human judgment cannot be
        # recorded outside Arbiter's normal control-plane history.
        self.store._audit(
            actor,
            "decision.recorded",
            "decision_record",
            record.decision_id,
            {
                "decision_type": record.decision_type,
                "cluster_id": record.cluster_id,
                "contract_id": record.contract_id,
                "affected_case_ids": record.affected_case_ids,
                "decision_hash": payload["decision_hash"],
                "supersedes": record.supersedes,
            },
        )
        return payload

    def get(self, decision_id: str) -> dict[str, Any] | None:
        with self.store.connect() as db:
            row = db.execute(
                "SELECT decision_json FROM decision_records WHERE decision_id=?",
                (decision_id,),
            ).fetchone()
        return json.loads(row["decision_json"]) if row else None

    def list(
        self,
        *,
        cluster_id: str | None = None,
        contract_id: str | None = None,
        decision_type: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        args: list[Any] = []
        if cluster_id:
            clauses.append("cluster_id=?")
            args.append(cluster_id)
        if contract_id:
            clauses.append("contract_id=?")
            args.append(contract_id)
        if decision_type:
            clauses.append("decision_type=?")
            args.append(decision_type)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        args.append(max(1, min(int(limit), 500)))
        with self.store.connect() as db:
            rows = db.execute(
                f"SELECT decision_json FROM decision_records {where} ORDER BY created_at DESC LIMIT ?",
                tuple(args),
            ).fetchall()
        return [json.loads(row["decision_json"]) for row in rows]

    def related_precedents(
        self,
        *,
        decision_type: str,
        governing_rule: str = "",
        exclude_cluster_id: str | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Return deterministic precedent candidates before semantic retrieval exists.

        v0.34 intentionally avoids pretending this is semantic similarity. It ranks
        same-type prior decisions first, with a small exact-rule bonus. A later
        retrieval layer can replace the ranking without changing DecisionRecord.
        """
        candidates = self.list(decision_type=decision_type, limit=200)
        scored: list[tuple[int, dict[str, Any]]] = []
        normalized_rule = " ".join(governing_rule.lower().split())
        for record in candidates:
            if exclude_cluster_id and record.get("cluster_id") == exclude_cluster_id:
                continue
            score = 10
            candidate_rule = " ".join(str(record.get("governing_rule") or "").lower().split())
            if normalized_rule and candidate_rule == normalized_rule:
                score += 10
            elif normalized_rule and candidate_rule and (
                normalized_rule in candidate_rule or candidate_rule in normalized_rule
            ):
                score += 4
            scored.append((score, record))
        scored.sort(key=lambda pair: (pair[0], pair[1].get("created_at", "")), reverse=True)
        return [record for _, record in scored[: max(1, min(limit, 20))]]

    def posture(self) -> dict[str, Any]:
        records = self.list(limit=500)
        return {
            "schema": "arbiter.decision-record.v1",
            "count": len(records),
            "decision_types": sorted({r.get("decision_type") for r in records if r.get("decision_type")}),
            "boundary": (
                "Decision records capture governed human judgment and precedent. "
                "They do not directly mutate contract terms, evidence, resolution outcomes, or settlement authorization."
            ),
        }

    def is_superseded(self, decision_id: str) -> bool:
        """True when some other decision record supersedes this one."""
        with self.store.connect() as db:
            row = db.execute(
                "SELECT 1 FROM decision_records WHERE supersedes=? LIMIT 1",
                (decision_id,),
            ).fetchone()
        return row is not None

    def authoritative(
        self,
        *,
        cluster_id: str | None = None,
        contract_id: str | None = None,
        decision_type: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Recorded decisions that nothing else supersedes. A superseded decision
        is retained (append-only history) but is no longer authoritative."""
        records = self.list(cluster_id=cluster_id, contract_id=contract_id, decision_type=decision_type, limit=500)
        live = [r for r in records if not self.is_superseded(r["decision_id"])]
        return live[: max(1, min(int(limit), 500))]


_service: DecisionRecordService | None = None


def get_service(resolution_store) -> DecisionRecordService:
    global _service
    if _service is None or _service.store is not resolution_store:
        _service = DecisionRecordService(resolution_store)
    return _service
