"""v0.12 governed approvals and settlement handoff controls.

This module deliberately stops at a signed authorization packet. It does not call an
exchange settlement endpoint or an oracle. Exchange-specific execution remains outside
Arbiter unless/until a dedicated adapter is explicitly configured and independently
approved.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from typing import Any

from .enterprise import load_runtime_config
from .resolution_infra import canonical_hash, gen_id, utcnow


TERMINAL_ACTIONS = {
    "kalshi_dcm": "prepare_exchange_resolution_authorization",
    "polymarket_uma": "prepare_oracle_proposal_or_dispute_packet",
    "generic": "prepare_resolution_authorization_packet",
}


class ApprovalControlService:
    def __init__(self, store):
        self.store = store
        self._init_db()

    def _init_db(self):
        with self.store.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS approval_requests (
                    approval_id TEXT PRIMARY KEY,
                    object_type TEXT NOT NULL,
                    object_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    exchange_profile TEXT NOT NULL DEFAULT 'generic',
                    requested_by TEXT NOT NULL,
                    requested_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    required_approvals INTEGER NOT NULL DEFAULT 1,
                    rationale TEXT NOT NULL DEFAULT '',
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE INDEX IF NOT EXISTS ix_approval_requests_object
                    ON approval_requests(object_type, object_id, requested_at DESC);

                CREATE TABLE IF NOT EXISTS approval_decisions (
                    decision_id TEXT PRIMARY KEY,
                    approval_id TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    note TEXT NOT NULL DEFAULT '',
                    decided_at TEXT NOT NULL,
                    FOREIGN KEY(approval_id) REFERENCES approval_requests(approval_id)
                );
                CREATE UNIQUE INDEX IF NOT EXISTS ux_approval_decision_actor
                    ON approval_decisions(approval_id, actor);

                CREATE TABLE IF NOT EXISTS settlement_packets (
                    packet_id TEXT PRIMARY KEY,
                    approval_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    contract_id TEXT NOT NULL,
                    contract_version INTEGER NOT NULL,
                    policy_version TEXT NOT NULL,
                    exchange_profile TEXT NOT NULL,
                    terminal_action TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    signature TEXT NOT NULL,
                    signing_key_id TEXT NOT NULL,
                    signature_mode TEXT NOT NULL,
                    production_eligible INTEGER NOT NULL DEFAULT 0,
                    UNIQUE(approval_id)
                );
                CREATE INDEX IF NOT EXISTS ix_settlement_packets_run
                    ON settlement_packets(run_id, created_at DESC);
                """
            )

    def _row(self, row):
        if not row:
            return None
        d = dict(row)
        for k in ("metadata_json", "payload_json"):
            if k in d:
                d[k[:-5]] = json.loads(d.pop(k) or "{}")
        if "production_eligible" in d:
            d["production_eligible"] = bool(d["production_eligible"])
        return d

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self.store.connect() as db:
            row = db.execute("SELECT run_json FROM resolution_runs WHERE run_id=?", (run_id,)).fetchone()
        return json.loads(row["run_json"]) if row else None

    def request_approval(self, *, object_type: str, object_id: str, action: str,
                         exchange_profile: str, requested_by: str, rationale: str = "",
                         required_approvals: int = 1, metadata: dict | None = None) -> dict:
        if required_approvals < 1 or required_approvals > 5:
            raise ValueError("required_approvals must be between 1 and 5")
        if object_type == "resolution_run":
            run = self.get_run(object_id)
            if not run:
                raise ValueError("resolution run not found")
            if run.get("state") != "completed":
                raise ValueError("only completed resolution runs may enter settlement approval")
            if str(run.get("outcome", "")).upper() in {"HELD", "PENDING", "REVIEW", "BLOCK"}:
                raise ValueError("held/pending resolution runs cannot enter settlement approval")
        aid = gen_id("apr")
        now = utcnow()
        with self.store.connect() as db:
            db.execute(
                "INSERT INTO approval_requests(approval_id,object_type,object_id,action,exchange_profile,requested_by,requested_at,status,required_approvals,rationale,metadata_json) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (aid, object_type, object_id, action, exchange_profile, requested_by, now, "pending",
                 required_approvals, rationale, json.dumps(metadata or {}, sort_keys=True)),
            )
        self.store._audit(requested_by, "approval.requested", object_type, object_id,
                          {"approval_id": aid, "action": action, "required_approvals": required_approvals,
                           "exchange_profile": exchange_profile})
        return self.get_approval(aid)

    def get_approval(self, approval_id: str) -> dict | None:
        with self.store.connect() as db:
            row = db.execute("SELECT * FROM approval_requests WHERE approval_id=?", (approval_id,)).fetchone()
            if not row:
                return None
            decisions = db.execute("SELECT * FROM approval_decisions WHERE approval_id=? ORDER BY decided_at", (approval_id,)).fetchall()
        d = self._row(row)
        d["decisions"] = [dict(x) for x in decisions]
        d["approval_count"] = sum(1 for x in d["decisions"] if x["decision"] == "approve")
        return d

    def list_approvals(self, status: str | None = None, object_id: str | None = None, limit: int = 100) -> list[dict]:
        sql = "SELECT approval_id FROM approval_requests WHERE 1=1"
        args: list[Any] = []
        if status:
            sql += " AND status=?"; args.append(status)
        if object_id:
            sql += " AND object_id=?"; args.append(object_id)
        sql += " ORDER BY requested_at DESC LIMIT ?"; args.append(limit)
        with self.store.connect() as db:
            rows = db.execute(sql, args).fetchall()
        return [self.get_approval(r["approval_id"]) for r in rows]

    def decide(self, approval_id: str, *, actor: str, decision: str, note: str = "") -> dict:
        req = self.get_approval(approval_id)
        if not req:
            raise ValueError("approval request not found")
        if req["status"] not in {"pending", "approved"}:
            raise ValueError("approval request is no longer actionable")
        if actor == req["requested_by"]:
            raise ValueError("maker-checker violation: requester cannot approve or reject own request")
        decision = decision.lower().strip()
        if decision not in {"approve", "reject"}:
            raise ValueError("decision must be approve or reject")
        did = gen_id("dec")
        try:
            with self.store.connect() as db:
                db.execute(
                    "INSERT INTO approval_decisions(decision_id,approval_id,actor,decision,note,decided_at) VALUES(?,?,?,?,?,?)",
                    (did, approval_id, actor, decision, note, utcnow()),
                )
        except Exception as e:
            if "UNIQUE" in str(e).upper():
                raise ValueError("actor has already decided this approval") from e
            raise
        req = self.get_approval(approval_id)
        if decision == "reject":
            status = "rejected"
        elif req["approval_count"] >= req["required_approvals"]:
            status = "approved"
        else:
            status = "pending"
        with self.store.connect() as db:
            db.execute("UPDATE approval_requests SET status=? WHERE approval_id=?", (status, approval_id))
        self.store._audit(actor, f"approval.{decision}d", req["object_type"], req["object_id"],
                          {"approval_id": approval_id, "decision_id": did, "status": status, "note": note})
        return self.get_approval(approval_id)

    def _sign(self, payload_hash: str) -> tuple[str, str, str, bool]:
        secret = os.environ.get("ARBITER_SETTLEMENT_SIGNING_SECRET")
        key_id = os.environ.get("ARBITER_SETTLEMENT_SIGNING_KEY_ID", "local-development")
        cfg = load_runtime_config()
        if secret:
            mode = "hmac-sha256"
            production_eligible = cfg.production
        else:
            # Explicitly non-production. This makes local integration/testing convenient without
            # pretending the packet is production-grade cryptographic authorization.
            secret = "arbiter-local-development-signing-key"
            mode = "local-development-hmac"
            production_eligible = False
        sig = hmac.new(secret.encode(), payload_hash.encode(), hashlib.sha256).hexdigest()
        return "hmac-sha256:" + sig, key_id, mode, production_eligible

    def create_settlement_packet(self, approval_id: str, *, actor: str) -> dict:
        req = self.get_approval(approval_id)
        if not req:
            raise ValueError("approval request not found")
        if req["status"] != "approved":
            raise ValueError("settlement packet requires an approved authorization request")
        if req["object_type"] != "resolution_run" or req["action"] != "authorize_settlement_handoff":
            raise ValueError("approval is not a settlement authorization")
        run = self.get_run(req["object_id"])
        if not run:
            raise ValueError("resolution run not found")
        # Fail closed again at packetization time.
        if run.get("state") != "completed" or str(run.get("outcome", "")).upper() in {"HELD", "PENDING", "REVIEW", "BLOCK"}:
            raise ValueError("resolution run is not settlement eligible")
        existing = self.packet_for_approval(approval_id)
        if existing:
            return existing
        profile = req.get("exchange_profile") or "generic"
        payload = {
            "schema": "arbiter.settlement-authorization.v1",
            "approval_id": approval_id,
            "resolution_run_id": run["run_id"],
            "run_hash": run.get("run_hash"),
            "contract_id": run["contract_id"],
            "contract_version": run["contract_version"],
            "policy_version": run["policy_version"],
            "engine_version": run["engine_version"],
            "outcome": run["outcome"],
            "evidence_ids": list(run.get("evidence_ids") or []),
            "approval_decisions": [
                {"actor": d["actor"], "decision": d["decision"], "decided_at": d["decided_at"]}
                for d in req["decisions"]
            ],
            "exchange_profile": profile,
            "terminal_action": TERMINAL_ACTIONS.get(profile, TERMINAL_ACTIONS["generic"]),
            "created_at": utcnow(),
        }
        payload_hash = canonical_hash(payload)
        signature, key_id, mode, production_eligible = self._sign(payload_hash)
        if load_runtime_config().production and not os.environ.get("ARBITER_SETTLEMENT_SIGNING_SECRET"):
            raise ValueError("production settlement packet signing secret is not configured")
        pid = gen_id("pkt")
        with self.store.connect() as db:
            db.execute(
                "INSERT INTO settlement_packets(packet_id,approval_id,run_id,contract_id,contract_version,policy_version,exchange_profile,terminal_action,created_at,created_by,payload_json,payload_hash,signature,signing_key_id,signature_mode,production_eligible) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (pid, approval_id, run["run_id"], run["contract_id"], run["contract_version"], run["policy_version"],
                 profile, payload["terminal_action"], payload["created_at"], actor, json.dumps(payload, sort_keys=True),
                 payload_hash, signature, key_id, mode, 1 if production_eligible else 0),
            )
        self.store._audit(actor, "settlement.packet.created", "resolution_run", run["run_id"],
                          {"packet_id": pid, "approval_id": approval_id, "payload_hash": payload_hash,
                           "exchange_profile": profile, "terminal_action": payload["terminal_action"],
                           "production_eligible": production_eligible})
        return self.packet_for_approval(approval_id)

    def packet_for_approval(self, approval_id: str) -> dict | None:
        with self.store.connect() as db:
            row = db.execute("SELECT * FROM settlement_packets WHERE approval_id=?", (approval_id,)).fetchone()
        return self._row(row)

    def list_packets(self, run_id: str | None = None, limit: int = 100) -> list[dict]:
        sql = "SELECT * FROM settlement_packets"
        args: list[Any] = []
        if run_id:
            sql += " WHERE run_id=?"; args.append(run_id)
        sql += " ORDER BY created_at DESC LIMIT ?"; args.append(limit)
        with self.store.connect() as db:
            rows = db.execute(sql, args).fetchall()
        return [self._row(r) for r in rows]

    def summary(self) -> dict:
        with self.store.connect() as db:
            approvals = db.execute("SELECT status,COUNT(*) n FROM approval_requests GROUP BY status").fetchall()
            packets = db.execute("SELECT COUNT(*) n FROM settlement_packets").fetchone()["n"]
        return {"approvals": {r["status"]: r["n"] for r in approvals}, "settlement_packets": packets,
                "boundary": "Signed handoff packets only; no exchange settlement or oracle transaction is executed by v0.12."}


_SERVICE = None

def get_service(store):
    global _SERVICE
    if _SERVICE is None or _SERVICE.store.path != store.path:
        _SERVICE = ApprovalControlService(store)
    return _SERVICE
