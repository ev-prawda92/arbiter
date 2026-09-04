"""Arbiter v0.11 active evidence infrastructure.

This module adds a durable, fail-closed observation layer around governed
Authority records. It deliberately stops short of settlement authorization:
evidence changes create deterministic re-evaluation requests and operational
exceptions, while the binding resolution/approval path remains separate.
"""
from __future__ import annotations

import hashlib
import json
import os
import urllib.request
import urllib.error
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from .resolution_infra import EvidenceRecord, ResolutionStore, canonical_hash, gen_id, utcnow


def _parse_time(value: str | None = None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _work_id(kind: str, subject: str) -> str:
    return "work_" + hashlib.sha256(f"{kind}|{subject}".encode()).hexdigest()[:14]


@dataclass(frozen=True)
class ObservationResult:
    status: str
    monitor_id: str
    evidence: dict[str, Any] | None
    changed: bool
    revision: bool
    conflict: bool
    reevaluation_request_id: str | None
    exception_id: str | None

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


class ActiveEvidenceService:
    def __init__(self, store: ResolutionStore):
        self.store = store
        self.init_db()

    def init_db(self) -> None:
        with self.store.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS evidence_monitors (
                    monitor_id TEXT PRIMARY KEY,
                    contract_id TEXT NOT NULL,
                    authority_id TEXT NOT NULL,
                    authority_version INTEGER NOT NULL,
                    adapter_type TEXT NOT NULL,
                    config_json TEXT NOT NULL,
                    schedule_seconds INTEGER NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    state TEXT NOT NULL DEFAULT 'idle',
                    consecutive_failures INTEGER NOT NULL DEFAULT 0,
                    last_polled_at TEXT,
                    next_poll_at TEXT,
                    last_success_at TEXT,
                    last_error TEXT,
                    last_payload_hash TEXT,
                    last_normalized_hash TEXT,
                    latest_evidence_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_evidence_monitors_due
                    ON evidence_monitors(enabled, next_poll_at);
                CREATE INDEX IF NOT EXISTS ix_evidence_monitors_contract
                    ON evidence_monitors(contract_id, authority_id);

                CREATE TABLE IF NOT EXISTS evidence_poll_runs (
                    poll_id TEXT PRIMARY KEY,
                    monitor_id TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    completed_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempt INTEGER NOT NULL,
                    details_json TEXT NOT NULL,
                    FOREIGN KEY(monitor_id) REFERENCES evidence_monitors(monitor_id)
                );
                CREATE INDEX IF NOT EXISTS ix_evidence_poll_monitor
                    ON evidence_poll_runs(monitor_id, started_at DESC);

                CREATE TABLE IF NOT EXISTS evidence_exceptions (
                    exception_id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    contract_id TEXT,
                    authority_id TEXT,
                    severity TEXT NOT NULL,
                    title TEXT NOT NULL,
                    detail TEXT NOT NULL,
                    recommended_action TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'open',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE INDEX IF NOT EXISTS ix_evidence_exceptions_status
                    ON evidence_exceptions(status, severity, updated_at DESC);

                CREATE TABLE IF NOT EXISTS resolution_reevaluation_requests (
                    request_id TEXT PRIMARY KEY,
                    contract_id TEXT NOT NULL,
                    evidence_id TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL,
                    completed_at TEXT,
                    UNIQUE(contract_id, evidence_id)
                );
                CREATE INDEX IF NOT EXISTS ix_resolution_reevaluation_pending
                    ON resolution_reevaluation_requests(status, created_at);
                """
            )

    def create_monitor(self, *, contract_id: str, authority_id: str, authority_version: int = 1,
                       adapter_type: str = "static", config: dict[str, Any] | None = None,
                       schedule_seconds: int = 300, enabled: bool = True,
                       actor: str = "system:evidence-ops") -> dict[str, Any]:
        if schedule_seconds < 60:
            raise ValueError("schedule_seconds must be >= 60")
        spec = self.store.latest_contract(contract_id)
        if not spec:
            raise ValueError("unknown contract")
        if authority_id not in (spec.get("authority_ids") or []):
            raise ValueError("authority is not governed by this contract specification")
        authority = self.store.get_authority(authority_id, authority_version)
        if not authority:
            raise ValueError("unknown authority/version")
        if authority.get("status") not in {"approved", "monitored"}:
            raise ValueError("authority is not eligible for active monitoring")
        adapter_type = adapter_type.lower().strip()
        if adapter_type not in {"static", "http_json"}:
            raise ValueError("adapter_type must be static or http_json")
        now = utcnow()
        monitor_id = gen_id("mon")
        cfg = config or {}
        with self.store.connect() as db:
            db.execute(
                "INSERT INTO evidence_monitors(monitor_id,contract_id,authority_id,authority_version,adapter_type,config_json,schedule_seconds,enabled,state,next_poll_at,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (monitor_id, contract_id, authority_id, authority_version, adapter_type, _json(cfg), schedule_seconds,
                 1 if enabled else 0, "idle", now, now, now),
            )
        self.store._audit(actor, "evidence.monitor.created", "evidence_monitor", monitor_id,
                          {"contract_id": contract_id, "authority_id": authority_id, "authority_version": authority_version,
                           "adapter_type": adapter_type, "schedule_seconds": schedule_seconds, "enabled": enabled})
        return self.get_monitor(monitor_id) or {}

    def get_monitor(self, monitor_id: str) -> dict[str, Any] | None:
        with self.store.connect() as db:
            r = db.execute("SELECT * FROM evidence_monitors WHERE monitor_id=?", (monitor_id,)).fetchone()
        if not r:
            return None
        out = dict(r)
        out["enabled"] = bool(out["enabled"])
        out["config"] = json.loads(out.pop("config_json"))
        return out

    def list_monitors(self, contract_id: str | None = None) -> list[dict[str, Any]]:
        with self.store.connect() as db:
            if contract_id:
                rows = db.execute("SELECT * FROM evidence_monitors WHERE contract_id=? ORDER BY created_at DESC", (contract_id,)).fetchall()
            else:
                rows = db.execute("SELECT * FROM evidence_monitors ORDER BY created_at DESC").fetchall()
        out = []
        for r in rows:
            d = dict(r); d["enabled"] = bool(d["enabled"]); d["config"] = json.loads(d.pop("config_json")); out.append(d)
        return out

    def update_monitor(self, monitor_id: str, *, config: dict[str, Any] | None = None,
                       enabled: bool | None = None, schedule_seconds: int | None = None,
                       actor: str = "system:evidence-ops") -> dict[str, Any]:
        current = self.get_monitor(monitor_id)
        if not current:
            raise ValueError("monitor not found")
        if schedule_seconds is not None and schedule_seconds < 60:
            raise ValueError("schedule_seconds must be >= 60")
        cfg = current["config"] if config is None else config
        enabled_value = current["enabled"] if enabled is None else enabled
        schedule = current["schedule_seconds"] if schedule_seconds is None else schedule_seconds
        now = utcnow()
        with self.store.connect() as db:
            db.execute("UPDATE evidence_monitors SET config_json=?,enabled=?,schedule_seconds=?,updated_at=? WHERE monitor_id=?",
                       (_json(cfg), 1 if enabled_value else 0, schedule, now, monitor_id))
        self.store._audit(actor, "evidence.monitor.updated", "evidence_monitor", monitor_id,
                          {"enabled": enabled_value, "schedule_seconds": schedule, "config_hash": canonical_hash(cfg)})
        return self.get_monitor(monitor_id) or {}

    def _latest_evidence(self, contract_id: str, authority_id: str) -> dict[str, Any] | None:
        with self.store.connect() as db:
            r = db.execute(
                "SELECT record_json FROM evidence_records WHERE contract_id=? AND authority_id=? ORDER BY revision_number DESC,retrieved_at DESC LIMIT 1",
                (contract_id, authority_id),
            ).fetchone()
        return json.loads(r["record_json"]) if r else None

    def _latest_other_evidence(self, contract_id: str, authority_id: str) -> list[dict[str, Any]]:
        with self.store.connect() as db:
            rows = db.execute(
                "SELECT e.record_json FROM evidence_records e JOIN (SELECT authority_id,MAX(retrieved_at) AS mx FROM evidence_records WHERE contract_id=? AND authority_id<>? GROUP BY authority_id) x ON e.authority_id=x.authority_id AND e.retrieved_at=x.mx WHERE e.contract_id=?",
                (contract_id, authority_id, contract_id),
            ).fetchall()
        return [json.loads(r["record_json"]) for r in rows]

    def _upsert_exception(self, *, kind: str, subject: str, contract_id: str | None, authority_id: str | None,
                          severity: str, title: str, detail: str, action: str,
                          metadata: dict[str, Any] | None = None, actor: str = "system:evidence-ops") -> dict[str, Any]:
        exception_id = "exc_" + hashlib.sha256(f"{kind}|{subject}".encode()).hexdigest()[:16]
        now = utcnow()
        with self.store.connect() as db:
            db.execute(
                "INSERT INTO evidence_exceptions(exception_id,kind,subject,contract_id,authority_id,severity,title,detail,recommended_action,status,created_at,updated_at,metadata_json) VALUES(?,?,?,?,?,?,?,?,?,'open',?,?,?) "
                "ON CONFLICT(exception_id) DO UPDATE SET severity=excluded.severity,title=excluded.title,detail=excluded.detail,recommended_action=excluded.recommended_action,status='open',updated_at=excluded.updated_at,metadata_json=excluded.metadata_json",
                (exception_id, kind, subject, contract_id, authority_id, severity, title, detail, action, now, now, _json(metadata or {})),
            )
        self.store.set_work_state(_work_id(kind, subject), "open", actor=actor, note=detail)
        self.store._audit(actor, "evidence.exception.opened", "evidence_exception", exception_id,
                          {"kind": kind, "subject": subject, "contract_id": contract_id, "authority_id": authority_id, "severity": severity})
        return self.get_exception(exception_id) or {}

    def get_exception(self, exception_id: str) -> dict[str, Any] | None:
        with self.store.connect() as db:
            r = db.execute("SELECT * FROM evidence_exceptions WHERE exception_id=?", (exception_id,)).fetchone()
        if not r: return None
        d = dict(r); d["metadata"] = json.loads(d.pop("metadata_json")); d["work_item_id"] = _work_id(d["kind"], d["subject"]); return d

    def list_exceptions(self, active_only: bool = True) -> list[dict[str, Any]]:
        with self.store.connect() as db:
            if active_only:
                rows = db.execute("SELECT * FROM evidence_exceptions WHERE status<>'resolved' ORDER BY updated_at DESC").fetchall()
            else:
                rows = db.execute("SELECT * FROM evidence_exceptions ORDER BY updated_at DESC").fetchall()
        out=[]
        for r in rows:
            d=dict(r); d["metadata"]=json.loads(d.pop("metadata_json")); d["work_item_id"]=_work_id(d["kind"],d["subject"]); out.append(d)
        return out

    def _request_reevaluation(self, contract_id: str, evidence_id: str, reason: str, actor: str) -> str:
        request_id = gen_id("reeval")
        now = utcnow()
        with self.store.connect() as db:
            existing = db.execute("SELECT request_id FROM resolution_reevaluation_requests WHERE contract_id=? AND evidence_id=?", (contract_id,evidence_id)).fetchone()
            if existing: return existing["request_id"]
            db.execute("INSERT INTO resolution_reevaluation_requests(request_id,contract_id,evidence_id,reason,status,created_at) VALUES(?,?,?,?,?,?)",
                       (request_id, contract_id, evidence_id, reason, "pending", now))
        self.store._audit(actor, "resolution.reevaluation.requested", "resolution_reevaluation", request_id,
                          {"contract_id": contract_id, "evidence_id": evidence_id, "reason": reason})
        return request_id

    def observe(self, monitor_id: str, *, normalized_value: Any, raw_payload: Any,
                observed_at: str | None = None, source_locator: str = "", parser_version: str = "active-evidence.v1",
                actor: str = "system:evidence-worker") -> ObservationResult:
        mon = self.get_monitor(monitor_id)
        if not mon: raise ValueError("monitor not found")
        if not mon["enabled"]: raise ValueError("monitor is disabled")
        now = utcnow(); raw_hash = canonical_hash(raw_payload); normalized_hash = canonical_hash(normalized_value)
        previous = self._latest_evidence(mon["contract_id"], mon["authority_id"])
        if previous and previous.get("raw_payload_hash") == raw_hash and canonical_hash(previous.get("normalized_value")) == normalized_hash:
            self._record_poll(monitor_id, "duplicate", {"raw_payload_hash": raw_hash}, attempt=1)
            self._mark_success(mon, raw_hash, normalized_hash, previous.get("evidence_id"), state="healthy")
            self.store._audit(actor, "evidence.duplicate.ignored", "evidence_monitor", monitor_id,
                              {"contract_id": mon["contract_id"], "authority_id": mon["authority_id"], "raw_payload_hash": raw_hash})
            return ObservationResult("duplicate", monitor_id, previous, False, False, False, None, None)

        revision = bool(previous)
        revision_number = int(previous.get("revision_number", 0)) + 1 if previous else 1
        record = EvidenceRecord(
            evidence_id=gen_id("evid"), authority_id=mon["authority_id"], authority_version=mon["authority_version"],
            observed_at=observed_at or now, retrieved_at=now, normalized_value=normalized_value,
            raw_payload_hash=raw_hash, parser_version=parser_version, contract_id=mon["contract_id"],
            effective_at=observed_at or now, revision_number=revision_number,
            supersedes=previous.get("evidence_id") if previous else None,
            source_locator=source_locator or (self.store.get_authority(mon["authority_id"], mon["authority_version"]) or {}).get("endpoint", ""),
            metadata={"monitor_id": monitor_id, "adapter_type": mon["adapter_type"], "normalized_hash": normalized_hash},
        )
        saved = self.store.append_evidence(record, actor=actor)
        conflict = False; exception_id = None
        for other in self._latest_other_evidence(mon["contract_id"], mon["authority_id"]):
            if canonical_hash(other.get("normalized_value")) != normalized_hash:
                conflict = True
                exc = self._upsert_exception(
                    kind="evidence_conflict", subject=mon["contract_id"], contract_id=mon["contract_id"], authority_id=mon["authority_id"],
                    severity="critical", title=f"Conflicting governed evidence: {mon['contract_id']}",
                    detail=f"{mon['authority_id']} produced a value that differs from another governed authority.",
                    action="Hold automated settlement and review source precedence, observation timing, and revision policy.",
                    metadata={"evidence_id": saved["evidence_id"], "other_evidence_id": other.get("evidence_id")}, actor=actor)
                exception_id = exc["exception_id"]
                break
        reeval = self._request_reevaluation(mon["contract_id"], saved["evidence_id"], "governed_evidence_changed", actor)
        status = "conflict" if conflict else ("revision" if revision else "appended")
        self._record_poll(monitor_id, status, {"evidence_id": saved["evidence_id"], "revision_number": revision_number, "conflict": conflict}, attempt=1)
        self._mark_success(mon, raw_hash, normalized_hash, saved["evidence_id"], state="conflict" if conflict else "healthy")
        return ObservationResult(status, monitor_id, saved, True, revision, conflict, reeval, exception_id)

    def _fetch(self, mon: dict[str, Any]) -> tuple[Any, Any, str]:
        cfg = mon["config"]
        if cfg.get("simulate_error"):
            raise RuntimeError(str(cfg["simulate_error"]))
        if mon["adapter_type"] == "static":
            if "value" not in cfg: raise RuntimeError("static adapter requires config.value")
            raw = cfg.get("raw", {"value": cfg["value"]})
            return cfg["value"], raw, str(cfg.get("source_locator") or "static://fixture")
        if os.environ.get("ARBITER_ENABLE_HTTP_SOURCE_ADAPTERS", "false").lower() not in {"1","true","yes"}:
            raise RuntimeError("http_json adapter disabled; set ARBITER_ENABLE_HTTP_SOURCE_ADAPTERS=true")
        authority = self.store.get_authority(mon["authority_id"], mon["authority_version"]) or {}
        endpoint = str(authority.get("endpoint") or "")
        if not endpoint.startswith("https://"):
            raise RuntimeError("http_json requires an approved HTTPS authority endpoint")
        req = urllib.request.Request(endpoint, headers={"User-Agent":"Arbiter-Evidence/0.11"})
        with urllib.request.urlopen(req, timeout=float(cfg.get("timeout_seconds", 10))) as resp:
            raw_bytes = resp.read(int(cfg.get("max_bytes", 1_000_000)) + 1)
            if len(raw_bytes) > int(cfg.get("max_bytes", 1_000_000)): raise RuntimeError("source payload exceeds max_bytes")
            payload = json.loads(raw_bytes.decode("utf-8"))
        value = payload
        path = str(cfg.get("json_path") or "").strip()
        if path:
            for part in path.split("."):
                value = value[int(part)] if isinstance(value, list) else value[part]
        return value, payload, endpoint

    def poll(self, monitor_id: str, actor: str = "system:evidence-worker") -> dict[str, Any]:
        mon = self.get_monitor(monitor_id)
        if not mon: raise ValueError("monitor not found")
        started = utcnow(); attempt = int(mon["consecutive_failures"]) + 1
        try:
            value, raw, locator = self._fetch(mon)
            result = self.observe(monitor_id, normalized_value=value, raw_payload=raw, source_locator=locator, actor=actor)
            return {"poll_started_at": started, **result.to_dict()}
        except Exception as e:
            failures = int(mon["consecutive_failures"]) + 1
            backoff = min(int(mon["schedule_seconds"]) * (2 ** max(0, failures - 1)), 3600)
            next_poll = (_parse_time() + timedelta(seconds=backoff)).isoformat()
            now = utcnow()
            with self.store.connect() as db:
                db.execute("UPDATE evidence_monitors SET state='outage',consecutive_failures=?,last_polled_at=?,next_poll_at=?,last_error=?,updated_at=? WHERE monitor_id=?",
                           (failures, now, next_poll, str(e)[:1000], now, monitor_id))
            exc = self._upsert_exception(kind="source_outage", subject=monitor_id, contract_id=mon["contract_id"], authority_id=mon["authority_id"],
                severity="high" if failures < 3 else "critical", title=f"Evidence source unavailable: {mon['authority_id']}",
                detail=f"Active evidence poll failed ({failures} consecutive): {str(e)[:300]}",
                action="Keep settlement fail-closed; verify source health and approved fallback policy before resolution.",
                metadata={"monitor_id": monitor_id, "consecutive_failures": failures, "next_poll_at": next_poll}, actor=actor)
            self._record_poll(monitor_id, "outage", {"error": str(e), "consecutive_failures": failures, "next_poll_at": next_poll}, attempt=attempt)
            self.store._audit(actor, "evidence.poll.failed", "evidence_monitor", monitor_id,
                              {"error": str(e)[:500], "consecutive_failures": failures, "next_poll_at": next_poll})
            return {"poll_started_at": started, "status":"outage", "monitor_id":monitor_id, "error":str(e), "consecutive_failures":failures, "next_poll_at":next_poll, "exception_id":exc["exception_id"]}

    def _mark_success(self, mon: dict[str, Any], raw_hash: str, normalized_hash: str, evidence_id: str | None, state: str) -> None:
        now = utcnow(); nxt = (_parse_time() + timedelta(seconds=int(mon["schedule_seconds"]))).isoformat()
        with self.store.connect() as db:
            db.execute("UPDATE evidence_monitors SET state=?,consecutive_failures=0,last_polled_at=?,next_poll_at=?,last_success_at=?,last_error=NULL,last_payload_hash=?,last_normalized_hash=?,latest_evidence_id=?,updated_at=? WHERE monitor_id=?",
                       (state, now, nxt, now, raw_hash, normalized_hash, evidence_id, now, mon["monitor_id"]))

    def _record_poll(self, monitor_id: str, status: str, details: dict[str, Any], attempt: int) -> None:
        now=utcnow()
        with self.store.connect() as db:
            db.execute("INSERT INTO evidence_poll_runs(poll_id,monitor_id,started_at,completed_at,status,attempt,details_json) VALUES(?,?,?,?,?,?,?)",
                       (gen_id("poll"), monitor_id, now, now, status, attempt, _json(details)))

    def poll_due(self, limit: int = 50, actor: str = "system:evidence-worker") -> dict[str, Any]:
        now=utcnow()
        with self.store.connect() as db:
            rows=db.execute("SELECT monitor_id FROM evidence_monitors WHERE enabled=1 AND (next_poll_at IS NULL OR next_poll_at<=?) ORDER BY COALESCE(next_poll_at,created_at) LIMIT ?",(now,limit)).fetchall()
        results=[self.poll(r["monitor_id"],actor=actor) for r in rows]
        return {"due":len(rows),"processed":len(results),"results":results}

    def list_reevaluations(self, status: str | None = None) -> list[dict[str, Any]]:
        with self.store.connect() as db:
            if status:
                rows=db.execute("SELECT * FROM resolution_reevaluation_requests WHERE status=? ORDER BY created_at DESC",(status,)).fetchall()
            else:
                rows=db.execute("SELECT * FROM resolution_reevaluation_requests ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]

    def source_health(self) -> dict[str, Any]:
        monitors=self.list_monitors(); active=[m for m in monitors if m["enabled"]]
        states={k:sum(1 for m in active if m["state"]==k) for k in {"idle","healthy","conflict","outage"}}
        return {"monitors":len(monitors),"active":len(active),"states":states,"healthy":all(m["state"] not in {"outage","conflict"} for m in active),"generated_at":utcnow()}

    def summary(self) -> dict[str, Any]:
        with self.store.connect() as db:
            def count(t): return int(db.execute(f"SELECT COUNT(*) n FROM {t}").fetchone()["n"])
            return {"monitors":count("evidence_monitors"),"poll_runs":count("evidence_poll_runs"),"exceptions":count("evidence_exceptions"),"pending_reevaluations":int(db.execute("SELECT COUNT(*) n FROM resolution_reevaluation_requests WHERE status='pending'").fetchone()["n"]),"source_health":self.source_health()}


service: ActiveEvidenceService | None = None

def get_service(store: ResolutionStore) -> ActiveEvidenceService:
    global service
    if service is None or service.store.path != store.path:
        service = ActiveEvidenceService(store)
    return service
