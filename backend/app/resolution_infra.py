"""Arbiter v0.6 resolution infrastructure.

Persistent domain primitives for mission-critical resolution control:
- ResolutionSpecification: canonical machine-readable contract semantics
- Authority: governed source definition and version
- EvidenceRecord: append-only normalized external observation
- ResolutionRun: replayable execution tying contract + policy + evidence + engine
- AuditEvent: append-only control-plane event log

The module intentionally uses sqlite3 from the standard library for the local
reference implementation.  Production can move the same schema behind
PostgreSQL without changing the domain contracts exposed by this module.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import uuid
from dataclasses import asdict, dataclass, field as dc_field
from datetime import datetime, timezone
from typing import Any, Iterable

HERE = os.path.dirname(__file__)
DB_PATH = os.environ.get(
    "ARBITER_DATABASE_PATH",
    os.path.abspath(os.path.join(HERE, "..", "data", "arbiter.db")),
)


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def gen_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def canonical_hash(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class ResolutionSpecification:
    contract_id: str
    contract_version: int
    title: str
    definition: dict[str, Any]
    timing: dict[str, Any]
    authority_ids: list[str]
    source_precedence: list[str] = dc_field(default_factory=list)
    revision_policy: dict[str, Any] = dc_field(default_factory=dict)
    fallback_policy: dict[str, Any] = dc_field(default_factory=dict)
    approval_policy: dict[str, Any] = dc_field(default_factory=dict)
    metadata: dict[str, Any] = dc_field(default_factory=dict)
    schema: str = "arbiter.resolution-spec.v1"

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.contract_id:
            errors.append("contract_id is required")
        if self.contract_version < 1:
            errors.append("contract_version must be >= 1")
        if not self.title.strip():
            errors.append("title is required")
        if not self.definition:
            errors.append("definition is required")
        if not self.timing:
            errors.append("timing is required")
        if not self.authority_ids:
            errors.append("at least one authority_id is required")
        if len(self.authority_ids) > 1 and not self.source_precedence:
            errors.append("multiple authorities require source_precedence")
        return errors

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["spec_hash"] = canonical_hash(d)
        return d


@dataclass(frozen=True)
class Authority:
    authority_id: str
    version: int
    name: str
    organization: str
    source_type: str
    endpoint: str = ""
    dataset: str = ""
    field: str = ""
    precision: str = ""
    revision_behavior: dict[str, Any] = dc_field(default_factory=dict)
    availability_policy: dict[str, Any] = dc_field(default_factory=dict)
    approved_contract_classes: list[str] = dc_field(default_factory=list)
    status: str = "approved"  # approved | monitored | suspended | retired
    metadata: dict[str, Any] = dc_field(default_factory=dict)
    schema: str = "arbiter.authority.v1"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["authority_hash"] = canonical_hash(d)
        return d


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    authority_id: str
    authority_version: int
    observed_at: str
    retrieved_at: str
    normalized_value: Any
    raw_payload_hash: str
    parser_version: str
    contract_id: str | None = None
    effective_at: str | None = None
    revision_number: int = 1
    supersedes: str | None = None
    source_locator: str = ""
    metadata: dict[str, Any] = dc_field(default_factory=dict)
    schema: str = "arbiter.evidence-record.v1"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["record_hash"] = canonical_hash(d)
        return d


@dataclass(frozen=True)
class ResolutionRun:
    run_id: str
    contract_id: str
    contract_version: int
    policy_version: str
    engine_version: str
    evidence_ids: list[str]
    control_results: list[dict[str, Any]]
    state: str
    outcome: str
    started_at: str
    completed_at: str | None = None
    exceptions: list[dict[str, Any]] = dc_field(default_factory=list)
    approvals: list[dict[str, Any]] = dc_field(default_factory=list)
    result: dict[str, Any] = dc_field(default_factory=dict)
    schema: str = "arbiter.resolution-run.v1"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["run_hash"] = canonical_hash(d)
        return d


class ResolutionStore:
    """Durable local reference store with append-oriented domain semantics."""

    def __init__(self, path: str = DB_PATH):
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.init_db()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def init_db(self) -> None:
        with self.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS contract_versions (
                    contract_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    spec_json TEXT NOT NULL,
                    spec_hash TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'draft',
                    PRIMARY KEY (contract_id, version)
                );
                CREATE INDEX IF NOT EXISTS ix_contract_versions_status
                    ON contract_versions(status);

                CREATE TABLE IF NOT EXISTS authority_versions (
                    authority_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    authority_json TEXT NOT NULL,
                    authority_hash TEXT NOT NULL,
                    status TEXT NOT NULL,
                    PRIMARY KEY (authority_id, version)
                );
                CREATE INDEX IF NOT EXISTS ix_authority_status
                    ON authority_versions(status);

                CREATE TABLE IF NOT EXISTS evidence_records (
                    evidence_id TEXT PRIMARY KEY,
                    authority_id TEXT NOT NULL,
                    authority_version INTEGER NOT NULL,
                    contract_id TEXT,
                    retrieved_at TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    revision_number INTEGER NOT NULL,
                    supersedes TEXT,
                    record_json TEXT NOT NULL,
                    record_hash TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_evidence_contract
                    ON evidence_records(contract_id, retrieved_at);
                CREATE INDEX IF NOT EXISTS ix_evidence_authority
                    ON evidence_records(authority_id, retrieved_at);

                CREATE TABLE IF NOT EXISTS resolution_runs (
                    run_id TEXT PRIMARY KEY,
                    contract_id TEXT NOT NULL,
                    contract_version INTEGER NOT NULL,
                    policy_version TEXT NOT NULL,
                    engine_version TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    state TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    run_json TEXT NOT NULL,
                    run_hash TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_resolution_runs_contract
                    ON resolution_runs(contract_id, started_at);

                CREATE TABLE IF NOT EXISTS audit_events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    occurred_at TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    action TEXT NOT NULL,
                    object_type TEXT NOT NULL,
                    object_id TEXT NOT NULL,
                    details_json TEXT NOT NULL,
                    previous_hash TEXT,
                    event_hash TEXT NOT NULL UNIQUE
                );
                CREATE INDEX IF NOT EXISTS ix_audit_object
                    ON audit_events(object_type, object_id, sequence);

                CREATE TABLE IF NOT EXISTS work_item_state (
                    work_item_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL DEFAULT 'open',
                    owner TEXT NOT NULL DEFAULT '',
                    note TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL,
                    updated_by TEXT NOT NULL
                );
                """
            )

    def _audit(self, actor: str, action: str, object_type: str, object_id: str, details: dict[str, Any]) -> dict:
        with self.connect() as db:
            prev = db.execute("SELECT event_hash FROM audit_events ORDER BY sequence DESC LIMIT 1").fetchone()
            previous_hash = prev["event_hash"] if prev else None
            event = {
                "event_id": gen_id("evt"),
                "occurred_at": utcnow(),
                "actor": actor,
                "action": action,
                "object_type": object_type,
                "object_id": object_id,
                "details": details,
                "previous_hash": previous_hash,
            }
            event_hash = canonical_hash(event)
            db.execute(
                "INSERT INTO audit_events(event_id,occurred_at,actor,action,object_type,object_id,details_json,previous_hash,event_hash) VALUES(?,?,?,?,?,?,?,?,?)",
                (event["event_id"], event["occurred_at"], actor, action, object_type, object_id,
                 json.dumps(details, sort_keys=True), previous_hash, event_hash),
            )
            event["event_hash"] = event_hash
            return event

    def save_contract(self, spec: ResolutionSpecification, actor: str = "system", status: str = "draft") -> dict[str, Any]:
        errors = spec.validate()
        if errors:
            raise ValueError("; ".join(errors))
        payload = spec.to_dict()
        with self.connect() as db:
            db.execute(
                "INSERT INTO contract_versions(contract_id,version,created_at,created_by,spec_json,spec_hash,status) VALUES(?,?,?,?,?,?,?)",
                (spec.contract_id, spec.contract_version, utcnow(), actor, json.dumps(payload, sort_keys=True), payload["spec_hash"], status),
            )
        self._audit(actor, "contract.version.created", "contract", spec.contract_id,
                    {"version": spec.contract_version, "status": status, "spec_hash": payload["spec_hash"]})
        return payload | {"status": status}

    def save_authority(self, authority: Authority, actor: str = "system") -> dict[str, Any]:
        payload = authority.to_dict()
        with self.connect() as db:
            db.execute(
                "INSERT INTO authority_versions(authority_id,version,created_at,created_by,authority_json,authority_hash,status) VALUES(?,?,?,?,?,?,?)",
                (authority.authority_id, authority.version, utcnow(), actor, json.dumps(payload, sort_keys=True), payload["authority_hash"], authority.status),
            )
        self._audit(actor, "authority.version.created", "authority", authority.authority_id,
                    {"version": authority.version, "status": authority.status, "authority_hash": payload["authority_hash"]})
        return payload

    def append_evidence(self, record: EvidenceRecord, actor: str = "system:evidence") -> dict[str, Any]:
        payload = record.to_dict()
        with self.connect() as db:
            auth = db.execute(
                "SELECT 1 FROM authority_versions WHERE authority_id=? AND version=?",
                (record.authority_id, record.authority_version),
            ).fetchone()
            if not auth:
                raise ValueError("unknown authority/version")
            if record.supersedes:
                old = db.execute("SELECT 1 FROM evidence_records WHERE evidence_id=?", (record.supersedes,)).fetchone()
                if not old:
                    raise ValueError("supersedes references unknown evidence")
            db.execute(
                "INSERT INTO evidence_records(evidence_id,authority_id,authority_version,contract_id,retrieved_at,observed_at,revision_number,supersedes,record_json,record_hash) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (record.evidence_id, record.authority_id, record.authority_version, record.contract_id,
                 record.retrieved_at, record.observed_at, record.revision_number, record.supersedes,
                 json.dumps(payload, sort_keys=True), payload["record_hash"]),
            )
        self._audit(actor, "evidence.appended", "evidence", record.evidence_id,
                    {"authority_id": record.authority_id, "contract_id": record.contract_id,
                     "revision_number": record.revision_number, "record_hash": payload["record_hash"]})
        return payload

    def save_run(self, run: ResolutionRun, actor: str = "system:resolver") -> dict[str, Any]:
        payload = run.to_dict()
        with self.connect() as db:
            contract = db.execute(
                "SELECT 1 FROM contract_versions WHERE contract_id=? AND version=?",
                (run.contract_id, run.contract_version),
            ).fetchone()
            if not contract:
                raise ValueError("unknown contract/version")
            for evidence_id in run.evidence_ids:
                if not db.execute("SELECT 1 FROM evidence_records WHERE evidence_id=?", (evidence_id,)).fetchone():
                    raise ValueError(f"unknown evidence_id: {evidence_id}")
            db.execute(
                "INSERT INTO resolution_runs(run_id,contract_id,contract_version,policy_version,engine_version,started_at,completed_at,state,outcome,run_json,run_hash) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (run.run_id, run.contract_id, run.contract_version, run.policy_version, run.engine_version,
                 run.started_at, run.completed_at, run.state, run.outcome,
                 json.dumps(payload, sort_keys=True), payload["run_hash"]),
            )
        self._audit(actor, "resolution.run.recorded", "resolution_run", run.run_id,
                    {"contract_id": run.contract_id, "contract_version": run.contract_version,
                     "state": run.state, "outcome": run.outcome, "run_hash": payload["run_hash"]})
        return payload

    def _json_rows(self, sql: str, args: Iterable[Any], field: str) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(sql, tuple(args)).fetchall()
            return [json.loads(r[field]) for r in rows]

    def list_contracts(self) -> list[dict[str, Any]]:
        return self._json_rows(
            "SELECT spec_json FROM contract_versions ORDER BY contract_id, version DESC", (), "spec_json"
        )

    def latest_contract(self, contract_id: str) -> dict[str, Any] | None:
        rows = self._json_rows(
            "SELECT spec_json FROM contract_versions WHERE contract_id=? ORDER BY version DESC LIMIT 1", (contract_id,), "spec_json"
        )
        return rows[0] if rows else None

    def list_authorities(self) -> list[dict[str, Any]]:
        return self._json_rows(
            "SELECT authority_json FROM authority_versions ORDER BY authority_id, version DESC", (), "authority_json"
        )

    def get_authority(self, authority_id: str, version: int | None = None) -> dict[str, Any] | None:
        if version is None:
            sql, args = "SELECT authority_json FROM authority_versions WHERE authority_id=? ORDER BY version DESC LIMIT 1", (authority_id,)
        else:
            sql, args = "SELECT authority_json FROM authority_versions WHERE authority_id=? AND version=?", (authority_id, version)
        rows = self._json_rows(sql, args, "authority_json")
        return rows[0] if rows else None

    def list_evidence(self, contract_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        if contract_id:
            sql, args = "SELECT record_json FROM evidence_records WHERE contract_id=? ORDER BY retrieved_at DESC LIMIT ?", (contract_id, limit)
        else:
            sql, args = "SELECT record_json FROM evidence_records ORDER BY retrieved_at DESC LIMIT ?", (limit,)
        return self._json_rows(sql, args, "record_json")

    def list_runs(self, contract_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        if contract_id:
            sql, args = "SELECT run_json FROM resolution_runs WHERE contract_id=? ORDER BY started_at DESC LIMIT ?", (contract_id, limit)
        else:
            sql, args = "SELECT run_json FROM resolution_runs ORDER BY started_at DESC LIMIT ?", (limit,)
        return self._json_rows(sql, args, "run_json")


    def list_work_states(self) -> dict[str, dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute("SELECT * FROM work_item_state ORDER BY updated_at DESC").fetchall()
        return {r["work_item_id"]: {
            "work_item_id": r["work_item_id"], "status": r["status"], "owner": r["owner"],
            "note": r["note"], "updated_at": r["updated_at"], "updated_by": r["updated_by"],
        } for r in rows}

    def set_work_state(self, work_item_id: str, status: str, owner: str = "", note: str = "", actor: str = "operator") -> dict[str, Any]:
        if status not in {"open", "in_progress", "resolved"}:
            raise ValueError("status must be open, in_progress, or resolved")
        now = utcnow()
        with self.connect() as db:
            db.execute(
                "INSERT INTO work_item_state(work_item_id,status,owner,note,updated_at,updated_by) VALUES(?,?,?,?,?,?) "
                "ON CONFLICT(work_item_id) DO UPDATE SET status=excluded.status, owner=excluded.owner, note=excluded.note, updated_at=excluded.updated_at, updated_by=excluded.updated_by",
                (work_item_id, status, owner, note, now, actor),
            )
        self._audit(actor, "work_item.updated", "work_item", work_item_id,
                    {"status": status, "owner": owner, "note": note})
        return {"work_item_id": work_item_id, "status": status, "owner": owner, "note": note, "updated_at": now, "updated_by": actor}

    def audit_log(self, limit: int = 100, object_type: str | None = None, object_id: str | None = None) -> list[dict[str, Any]]:
        clauses, args = [], []
        if object_type:
            clauses.append("object_type=?"); args.append(object_type)
        if object_id:
            clauses.append("object_id=?"); args.append(object_id)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        with self.connect() as db:
            rows = db.execute(
                f"SELECT * FROM audit_events{where} ORDER BY sequence DESC LIMIT ?",
                (*args, limit),
            ).fetchall()
            return [{
                "sequence": r["sequence"], "event_id": r["event_id"], "occurred_at": r["occurred_at"],
                "actor": r["actor"], "action": r["action"], "object_type": r["object_type"],
                "object_id": r["object_id"], "details": json.loads(r["details_json"]),
                "previous_hash": r["previous_hash"], "event_hash": r["event_hash"],
            } for r in rows]

    def verify_audit_chain(self) -> dict[str, Any]:
        with self.connect() as db:
            rows = db.execute("SELECT * FROM audit_events ORDER BY sequence ASC").fetchall()
        previous = None
        for r in rows:
            if r["previous_hash"] != previous:
                return {"ok": False, "sequence": r["sequence"], "reason": "previous_hash mismatch"}
            base = {
                "event_id": r["event_id"], "occurred_at": r["occurred_at"], "actor": r["actor"],
                "action": r["action"], "object_type": r["object_type"], "object_id": r["object_id"],
                "details": json.loads(r["details_json"]), "previous_hash": r["previous_hash"],
            }
            if canonical_hash(base) != r["event_hash"]:
                return {"ok": False, "sequence": r["sequence"], "reason": "event_hash mismatch"}
            previous = r["event_hash"]
        return {"ok": True, "events": len(rows), "head": previous}

    def summary(self) -> dict[str, Any]:
        with self.connect() as db:
            def count(table: str) -> int:
                return int(db.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"])
            return {
                "database": self.path,
                "contracts": count("contract_versions"),
                "authorities": count("authority_versions"),
                "evidence_records": count("evidence_records"),
                "resolution_runs": count("resolution_runs"),
                "audit_events": count("audit_events"),
                "work_item_states": count("work_item_state"),
                "audit_chain": self.verify_audit_chain(),
            }


store = ResolutionStore()


def seed_reference_data() -> dict[str, int]:
    """Seed a few canonical authorities for local/demo use. Idempotent."""
    authorities = [
        Authority(
            authority_id="AUTH-BLS-CPI", version=1, name="BLS Consumer Price Index",
            organization="U.S. Bureau of Labor Statistics", source_type="government_dataset",
            endpoint="https://www.bls.gov/cpi/", dataset="Consumer Price Index",
            field="CPI-U / published contract-specific field", precision="source-defined",
            revision_behavior={"policy": "contract_must_define_first_vs_revised_print"},
            availability_policy={"expected": "scheduled_release"},
            approved_contract_classes=["macro", "inflation"],
        ),
        Authority(
            authority_id="AUTH-FED-FOMC", version=1, name="Federal Reserve FOMC Statements",
            organization="Federal Reserve", source_type="official_publication",
            endpoint="https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
            dataset="FOMC statements", field="target federal funds range / action",
            approved_contract_classes=["macro", "rates"],
        ),
        Authority(
            authority_id="AUTH-NOAA-WEATHER", version=1, name="NOAA / National Weather Service",
            organization="NOAA / NWS", source_type="government_dataset",
            endpoint="https://www.weather.gov/", dataset="station observations and climate reports",
            field="contract-specific station observation", precision="station/report-defined",
            revision_behavior={"policy": "contract_must_define_revision_cutoff"},
            approved_contract_classes=["weather"],
        ),
    ]
    created = 0
    for authority in authorities:
        if store.get_authority(authority.authority_id, authority.version) is None:
            store.save_authority(authority, actor="system:seed")
            created += 1
    return {"authorities_created": created}
