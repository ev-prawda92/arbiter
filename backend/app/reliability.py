"""Arbiter v0.15 production reliability primitives.

Durable queueing, idempotency, signed webhook envelopes, dead-letter handling,
and operational posture. This is intentionally storage-local for development;
production deployments should run the same contracts on PostgreSQL/managed queues.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from .resolution_infra import canonical_hash, gen_id, utcnow


def _dt(value: str | None = None) -> datetime:
    if value:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


class ReliabilityService:
    def __init__(self, store):
        self.store = store
        self.init_db()

    def init_db(self) -> None:
        with self.store.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS operation_idempotency (
                    idempotency_key TEXT NOT NULL,
                    operation_scope TEXT NOT NULL,
                    request_hash TEXT NOT NULL,
                    response_json TEXT,
                    status_code INTEGER,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    PRIMARY KEY(idempotency_key, operation_scope)
                );
                CREATE INDEX IF NOT EXISTS ix_idempotency_expiry ON operation_idempotency(expires_at);

                CREATE TABLE IF NOT EXISTS durable_jobs (
                    job_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    job_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL DEFAULT 5,
                    available_at TEXT NOT NULL,
                    locked_at TEXT,
                    locked_by TEXT,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT
                );
                CREATE INDEX IF NOT EXISTS ix_jobs_due ON durable_jobs(status, available_at);
                CREATE INDEX IF NOT EXISTS ix_jobs_tenant ON durable_jobs(tenant_id, status, created_at);

                CREATE TABLE IF NOT EXISTS webhook_deliveries (
                    delivery_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    target_url TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    nonce TEXT NOT NULL UNIQUE,
                    timestamp TEXT NOT NULL,
                    signature TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL DEFAULT 5,
                    next_attempt_at TEXT NOT NULL,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    delivered_at TEXT
                );
                CREATE INDEX IF NOT EXISTS ix_webhooks_due ON webhook_deliveries(status, next_attempt_at);

                CREATE TABLE IF NOT EXISTS replay_nonces (
                    nonce TEXT PRIMARY KEY,
                    first_seen_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_replay_expiry ON replay_nonces(expires_at);

                CREATE TABLE IF NOT EXISTS schema_migrations (
                    migration_id TEXT PRIMARY KEY,
                    applied_at TEXT NOT NULL,
                    checksum TEXT NOT NULL,
                    description TEXT NOT NULL
                );
                """
            )
            row = db.execute("SELECT 1 FROM schema_migrations WHERE migration_id=?", ("v0.15-reliability",)).fetchone()
            if not row:
                checksum = canonical_hash({"migration": "v0.15-reliability", "tables": 5})
                db.execute(
                    "INSERT INTO schema_migrations(migration_id,applied_at,checksum,description) VALUES(?,?,?,?)",
                    ("v0.15-reliability", utcnow(), checksum, "durable reliability control tables"),
                )

    # ---- idempotency ----
    def idempotency_get(self, key: str, scope: str, request: Any) -> dict | None:
        req_hash = canonical_hash(request)
        with self.store.connect() as db:
            row = db.execute(
                "SELECT * FROM operation_idempotency WHERE idempotency_key=? AND operation_scope=?",
                (key, scope),
            ).fetchone()
        if not row:
            return None
        if _dt(row["expires_at"]) <= _dt():
            return None
        if row["request_hash"] != req_hash:
            raise ValueError("idempotency key reused with different request")
        return {
            "key": key, "scope": scope, "request_hash": req_hash,
            "response": json.loads(row["response_json"]) if row["response_json"] else None,
            "status_code": row["status_code"], "replayed": True,
        }

    def idempotency_put(self, key: str, scope: str, request: Any, response: Any, status_code: int = 200, ttl_seconds: int = 86400) -> dict:
        now = _dt(); exp = now + timedelta(seconds=max(60, ttl_seconds)); req_hash = canonical_hash(request)
        with self.store.connect() as db:
            existing = db.execute(
                "SELECT request_hash,response_json,status_code FROM operation_idempotency WHERE idempotency_key=? AND operation_scope=?",
                (key, scope),
            ).fetchone()
            if existing:
                if existing["request_hash"] != req_hash:
                    raise ValueError("idempotency key reused with different request")
                return {"key": key, "scope": scope, "request_hash": req_hash, "response": json.loads(existing["response_json"]), "status_code": existing["status_code"], "replayed": True}
            db.execute(
                "INSERT INTO operation_idempotency(idempotency_key,operation_scope,request_hash,response_json,status_code,created_at,expires_at) VALUES(?,?,?,?,?,?,?)",
                (key, scope, req_hash, json.dumps(response, sort_keys=True, default=str), status_code, _iso(now), _iso(exp)),
            )
        return {"key": key, "scope": scope, "request_hash": req_hash, "response": response, "status_code": status_code, "replayed": False}

    # ---- durable jobs ----
    def enqueue_job(self, job_type: str, payload: dict, tenant_id: str = "local", max_attempts: int = 5, available_at: str | None = None, actor: str = "system:queue") -> dict:
        if not job_type.strip(): raise ValueError("job_type is required")
        if max_attempts < 1 or max_attempts > 25: raise ValueError("max_attempts must be between 1 and 25")
        now = utcnow(); job_id = gen_id("job"); payload_hash = canonical_hash(payload)
        with self.store.connect() as db:
            db.execute(
                "INSERT INTO durable_jobs(job_id,tenant_id,job_type,payload_json,payload_hash,status,attempts,max_attempts,available_at,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (job_id, tenant_id, job_type, json.dumps(payload, sort_keys=True, default=str), payload_hash, "queued", 0, max_attempts, available_at or now, now, now),
            )
        self.store._audit(actor, "job.enqueued", "job", job_id, {"job_type": job_type, "tenant_id": tenant_id, "payload_hash": payload_hash})
        return self.get_job(job_id)

    def get_job(self, job_id: str) -> dict | None:
        with self.store.connect() as db:
            row = db.execute("SELECT * FROM durable_jobs WHERE job_id=?", (job_id,)).fetchone()
        return self._job(row) if row else None

    def _job(self, row) -> dict:
        d = dict(row); d["payload"] = json.loads(d.pop("payload_json")); return d

    def list_jobs(self, status: str | None = None, tenant_id: str | None = None, limit: int = 100) -> list[dict]:
        sql="SELECT * FROM durable_jobs"; where=[]; args=[]
        if status: where.append("status=?"); args.append(status)
        if tenant_id: where.append("tenant_id=?"); args.append(tenant_id)
        if where: sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY created_at DESC LIMIT ?"; args.append(limit)
        with self.store.connect() as db: rows=db.execute(sql,args).fetchall()
        return [self._job(r) for r in rows]

    def claim_job(self, worker_id: str, tenant_id: str | None = None, lease_seconds: int = 60) -> dict | None:
        if not worker_id.strip(): raise ValueError("worker_id is required")
        now=_dt(); stale=_iso(now-timedelta(seconds=max(5,lease_seconds)))
        with self.store.connect() as db:
            # Requeue expired leases first.
            db.execute("UPDATE durable_jobs SET status='queued',locked_at=NULL,locked_by=NULL,updated_at=? WHERE status='running' AND locked_at<?", (_iso(now), stale))
            if tenant_id:
                row=db.execute("SELECT job_id FROM durable_jobs WHERE status='queued' AND tenant_id=? AND available_at<=? ORDER BY available_at,created_at LIMIT 1",(tenant_id,_iso(now))).fetchone()
            else:
                row=db.execute("SELECT job_id FROM durable_jobs WHERE status='queued' AND available_at<=? ORDER BY available_at,created_at LIMIT 1",(_iso(now),)).fetchone()
            if not row: return None
            job_id=row["job_id"]
            cur=db.execute("UPDATE durable_jobs SET status='running',attempts=attempts+1,locked_at=?,locked_by=?,updated_at=? WHERE job_id=? AND status='queued'",(_iso(now),worker_id,_iso(now),job_id))
            if cur.rowcount != 1: return None
        self.store._audit(worker_id,"job.claimed","job",job_id,{})
        return self.get_job(job_id)

    def complete_job(self, job_id: str, worker_id: str, result: dict | None = None) -> dict:
        now=utcnow()
        with self.store.connect() as db:
            row=db.execute("SELECT * FROM durable_jobs WHERE job_id=?",(job_id,)).fetchone()
            if not row: raise ValueError("job not found")
            if row["status"] != "running": raise ValueError("job is not running")
            if row["locked_by"] != worker_id: raise PermissionError("job lease belongs to another worker")
            db.execute("UPDATE durable_jobs SET status='completed',completed_at=?,updated_at=?,locked_at=NULL,locked_by=NULL,last_error=NULL WHERE job_id=?",(now,now,job_id))
        self.store._audit(worker_id,"job.completed","job",job_id,{"result_hash":canonical_hash(result or {})})
        return self.get_job(job_id)

    def fail_job(self, job_id: str, worker_id: str, error: str, retry_delay_seconds: int = 30) -> dict:
        now=_dt()
        with self.store.connect() as db:
            row=db.execute("SELECT * FROM durable_jobs WHERE job_id=?",(job_id,)).fetchone()
            if not row: raise ValueError("job not found")
            if row["status"] != "running": raise ValueError("job is not running")
            if row["locked_by"] != worker_id: raise PermissionError("job lease belongs to another worker")
            terminal = int(row["attempts"]) >= int(row["max_attempts"])
            status="dead_letter" if terminal else "queued"
            available=_iso(now+timedelta(seconds=max(1,retry_delay_seconds)))
            db.execute("UPDATE durable_jobs SET status=?,available_at=?,updated_at=?,locked_at=NULL,locked_by=NULL,last_error=? WHERE job_id=?",(status,available,_iso(now),error[:2000],job_id))
        self.store._audit(worker_id,"job.dead_lettered" if terminal else "job.retry_scheduled","job",job_id,{"error":error[:500]})
        return self.get_job(job_id)

    # ---- signed webhook envelopes ----
    @staticmethod
    def _signing_secret() -> str:
        return os.environ.get("ARBITER_WEBHOOK_SIGNING_SECRET") or ("dev-webhook-secret" if os.environ.get("ARBITER_ENV","development").lower() not in {"prod","production"} else "")

    def create_webhook(self, event_type: str, target_url: str, payload: dict, tenant_id: str = "local", max_attempts: int = 5, actor: str = "system:webhook") -> dict:
        if not target_url.startswith("https://") and os.environ.get("ARBITER_ENV","development").lower() in {"prod","production"}:
            raise ValueError("production webhooks require https")
        secret=self._signing_secret()
        if not secret: raise ValueError("webhook signing secret is not configured")
        now=utcnow(); nonce=secrets.token_hex(16); delivery_id=gen_id("wh"); payload_hash=canonical_hash(payload)
        message=f"{now}.{nonce}.{payload_hash}".encode(); sig="sha256="+hmac.new(secret.encode(),message,hashlib.sha256).hexdigest()
        with self.store.connect() as db:
            db.execute("INSERT INTO webhook_deliveries(delivery_id,tenant_id,event_type,target_url,payload_json,payload_hash,nonce,timestamp,signature,status,attempts,max_attempts,next_attempt_at,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                       (delivery_id,tenant_id,event_type,target_url,json.dumps(payload,sort_keys=True,default=str),payload_hash,nonce,now,sig,"pending",0,max_attempts,now,now,now))
        self.store._audit(actor,"webhook.queued","webhook_delivery",delivery_id,{"event_type":event_type,"target_url":target_url,"payload_hash":payload_hash})
        return self.get_webhook(delivery_id)

    def get_webhook(self, delivery_id: str) -> dict | None:
        with self.store.connect() as db: row=db.execute("SELECT * FROM webhook_deliveries WHERE delivery_id=?",(delivery_id,)).fetchone()
        if not row: return None
        d=dict(row); d["payload"]=json.loads(d.pop("payload_json")); return d

    def verify_webhook(self, timestamp: str, nonce: str, payload: dict, signature: str, tolerance_seconds: int = 300, consume_nonce: bool = True) -> dict:
        secret=self._signing_secret()
        if not secret: return {"valid":False,"reason":"signing secret unavailable"}
        try: age=abs((_dt()-_dt(timestamp)).total_seconds())
        except Exception: return {"valid":False,"reason":"invalid timestamp"}
        if age > tolerance_seconds: return {"valid":False,"reason":"timestamp outside tolerance"}
        payload_hash=canonical_hash(payload); msg=f"{timestamp}.{nonce}.{payload_hash}".encode(); expected="sha256="+hmac.new(secret.encode(),msg,hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected,signature): return {"valid":False,"reason":"signature mismatch"}
        if consume_nonce:
            now=_dt(); exp=_iso(now+timedelta(seconds=tolerance_seconds))
            with self.store.connect() as db:
                db.execute("DELETE FROM replay_nonces WHERE expires_at<=?",(_iso(now),))
                if db.execute("SELECT 1 FROM replay_nonces WHERE nonce=?",(nonce,)).fetchone(): return {"valid":False,"reason":"replay detected"}
                db.execute("INSERT INTO replay_nonces(nonce,first_seen_at,expires_at) VALUES(?,?,?)",(nonce,_iso(now),exp))
        return {"valid":True,"reason":"verified","payload_hash":payload_hash}

    def posture(self) -> dict:
        with self.store.connect() as db:
            counts={}
            for status in ("queued","running","completed","dead_letter"):
                counts[status]=int(db.execute("SELECT COUNT(*) n FROM durable_jobs WHERE status=?",(status,)).fetchone()["n"])
            pending=int(db.execute("SELECT COUNT(*) n FROM webhook_deliveries WHERE status IN ('pending','retry')").fetchone()["n"])
            migrations=[dict(r) for r in db.execute("SELECT * FROM schema_migrations ORDER BY applied_at").fetchall()]
        prod=os.environ.get("ARBITER_ENV","development").lower() in {"prod","production"}
        findings=[]
        if prod and not os.environ.get("ARBITER_WEBHOOK_SIGNING_SECRET"):
            findings.append({"severity":"BLOCK","code":"WEBHOOK_SIGNING_SECRET_MISSING","detail":"Production webhook envelopes require ARBITER_WEBHOOK_SIGNING_SECRET or KMS/HSM-backed signing."})
        if prod and os.environ.get("ARBITER_DATABASE_BACKEND","sqlite").lower() != "postgresql":
            findings.append({"severity":"BLOCK","code":"RELIABILITY_STORE_NOT_POSTGRESQL","detail":"Production reliability state must use PostgreSQL/managed durable infrastructure."})
        return {"version":"0.15.0","jobs":counts,"pending_webhooks":pending,"migrations":migrations,"configuration_gate":"BLOCK" if any(x["severity"]=="BLOCK" for x in findings) else "PASS","findings":findings,"boundary":"Durability primitives are implemented. Production still requires managed PostgreSQL/queue infrastructure, HA deployment, external observability, and independent failure testing."}


_service=None

def get_service(store):
    global _service
    if _service is None or _service.store is not store:
        _service=ReliabilityService(store)
    return _service
