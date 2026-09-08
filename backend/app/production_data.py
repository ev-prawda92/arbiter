"""Arbiter v0.17 production data plane.

This module is the single infrastructure boundary for durable data services:
- SQLite remains a deterministic local/development reference backend.
- PostgreSQL is the production database backend.
- PostgreSQL sessions receive request-scoped tenant/principal context and use RLS.
- Content-addressed object storage preserves immutable evidence payloads.
- Transaction/serialization helpers protect concurrency-sensitive operations.
- Backup/restore manifests make local drills verifiable and define production posture.

Important: this module provides production-shaped controls; it does not claim a cloud
provider, managed database, object bucket, or backup service has actually been provisioned.
Those external resources must be deployed and independently validated before live settlement.
"""
from __future__ import annotations

import contextlib
import contextvars
import hashlib
import importlib.util
import json
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


# ---- request / worker data-plane context ------------------------------------
_TENANT = contextvars.ContextVar("arbiter_tenant_id", default=None)
_PRINCIPAL = contextvars.ContextVar("arbiter_principal_id", default=None)
_REQUEST_ID = contextvars.ContextVar("arbiter_request_id", default=None)


def bind_context(tenant_id: str | None, principal_id: str | None = None, request_id: str | None = None):
    """Bind the current execution context and return reset tokens."""
    return (
        _TENANT.set(tenant_id or None),
        _PRINCIPAL.set(principal_id or None),
        _REQUEST_ID.set(request_id or None),
    )


def reset_context(tokens) -> None:
    if not tokens:
        return
    _TENANT.reset(tokens[0]); _PRINCIPAL.reset(tokens[1]); _REQUEST_ID.reset(tokens[2])


def current_context() -> dict[str, str | None]:
    return {"tenant_id": _TENANT.get(), "principal_id": _PRINCIPAL.get(), "request_id": _REQUEST_ID.get()}


# ---- config -----------------------------------------------------------------
def _truthy(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class DataPlaneConfig:
    environment: str
    database_backend: str
    database_url: str
    database_sslmode: str
    object_store_backend: str
    object_store_root: str
    s3_bucket: str
    s3_prefix: str
    s3_kms_key_id: str
    backup_dir: str

    @property
    def production(self) -> bool:
        return self.environment in {"prod", "production"}


def load_config() -> DataPlaneConfig:
    environment = os.environ.get("ARBITER_ENV", "development").strip().lower()
    database_backend = os.environ.get("ARBITER_DATABASE_BACKEND", "sqlite").strip().lower()
    root_default = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "objects"))
    backup_default = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "backups"))
    return DataPlaneConfig(
        environment=environment,
        database_backend=database_backend,
        database_url=os.environ.get("ARBITER_DATABASE_URL", "").strip(),
        database_sslmode=os.environ.get("ARBITER_DATABASE_SSLMODE", "require" if environment in {"prod", "production"} else "prefer").strip(),
        object_store_backend=os.environ.get("ARBITER_OBJECT_STORE_BACKEND", "local").strip().lower(),
        object_store_root=os.environ.get("ARBITER_OBJECT_STORE_ROOT", root_default).strip(),
        s3_bucket=os.environ.get("ARBITER_S3_BUCKET", "").strip(),
        s3_prefix=os.environ.get("ARBITER_S3_PREFIX", "arbiter").strip().strip("/"),
        s3_kms_key_id=os.environ.get("ARBITER_S3_KMS_KEY_ID", "").strip(),
        backup_dir=os.environ.get("ARBITER_BACKUP_DIR", backup_default).strip(),
    )


def driver_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def configuration_findings() -> list[dict[str, Any]]:
    cfg = load_config(); findings: list[dict[str, Any]] = []
    if cfg.database_backend not in {"sqlite", "postgresql"}:
        findings.append({"severity":"BLOCK","code":"UNSUPPORTED_DATABASE_BACKEND","detail":"ARBITER_DATABASE_BACKEND must be sqlite or postgresql."})
    if cfg.production and cfg.database_backend != "postgresql":
        findings.append({"severity":"BLOCK","code":"PRODUCTION_DATA_PLANE_NOT_POSTGRESQL","detail":"Production requires PostgreSQL."})
    if cfg.database_backend == "postgresql" and not cfg.database_url:
        findings.append({"severity":"BLOCK","code":"POSTGRES_DATABASE_URL_MISSING","detail":"ARBITER_DATABASE_URL is required when PostgreSQL is selected."})
    if cfg.database_backend == "postgresql" and not driver_available("psycopg"):
        findings.append({"severity":"BLOCK","code":"PSYCOPG_DRIVER_MISSING","detail":"Install psycopg 3 for the PostgreSQL data plane."})
    if cfg.production and cfg.database_sslmode in {"disable", "allow"}:
        findings.append({"severity":"BLOCK","code":"POSTGRES_TLS_NOT_REQUIRED","detail":"Production PostgreSQL connections must require TLS."})
    if cfg.object_store_backend not in {"local", "s3"}:
        findings.append({"severity":"BLOCK","code":"UNSUPPORTED_OBJECT_STORE","detail":"ARBITER_OBJECT_STORE_BACKEND must be local or s3."})
    if cfg.production and cfg.object_store_backend != "s3":
        findings.append({"severity":"BLOCK","code":"PRODUCTION_OBJECT_STORE_NOT_MANAGED","detail":"Production evidence payloads require managed object storage (s3 adapter in v0.17)."})
    if cfg.object_store_backend == "s3" and not cfg.s3_bucket:
        findings.append({"severity":"BLOCK","code":"S3_BUCKET_MISSING","detail":"ARBITER_S3_BUCKET is required for the s3 object store."})
    if cfg.object_store_backend == "s3" and not driver_available("boto3"):
        findings.append({"severity":"BLOCK","code":"BOTO3_DRIVER_MISSING","detail":"Install boto3 for the s3 object-store adapter."})
    return findings


# ---- SQL compatibility / PostgreSQL sessions --------------------------------
def _qmark_to_pyformat(sql: str) -> str:
    """Translate sqlite qmark placeholders outside quoted strings to psycopg %s."""
    out: list[str] = []; single = double = False; i = 0
    while i < len(sql):
        ch = sql[i]
        if ch == "'" and not double:
            out.append(ch)
            if single and i + 1 < len(sql) and sql[i + 1] == "'":
                out.append("'"); i += 2; continue
            single = not single; i += 1; continue
        if ch == '"' and not single:
            out.append(ch); double = not double; i += 1; continue
        if ch == "?" and not single and not double:
            out.append("%s")
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def _split_sql_script(script: str) -> list[str]:
    statements: list[str] = []; current: list[str] = []; single = double = False; i = 0
    while i < len(script):
        ch = script[i]
        if ch == "'" and not double:
            current.append(ch)
            if single and i + 1 < len(script) and script[i + 1] == "'":
                current.append("'"); i += 2; continue
            single = not single
        elif ch == '"' and not single:
            current.append(ch); double = not double
        elif ch == ";" and not single and not double:
            stmt = "".join(current).strip()
            if stmt: statements.append(stmt)
            current = []
        else:
            current.append(ch)
        i += 1
    tail = "".join(current).strip()
    if tail: statements.append(tail)
    return statements


def _postgres_ddl(sql: str) -> str:
    sql = re.sub(r"INTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT", "BIGSERIAL PRIMARY KEY", sql, flags=re.I)
    return sql


class PostgresConnection:
    """Small adapter preserving the sqlite-like API used by existing Arbiter services."""
    def __init__(self, dsn: str, sslmode: str = "require"):
        self.dsn = dsn; self.sslmode = sslmode; self.conn = None

    def __enter__(self):
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as e:
            raise RuntimeError("PostgreSQL selected but psycopg is not installed") from e
        kwargs = {"row_factory": dict_row}
        # sslmode in the DSN wins; otherwise enforce configured mode.
        if "sslmode=" not in self.dsn:
            kwargs["sslmode"] = self.sslmode
        self.conn = psycopg.connect(self.dsn, **kwargs)
        self.conn.autocommit = False
        ctx = current_context()
        if ctx["tenant_id"]:
            self.conn.execute("SELECT set_config('arbiter.tenant_id', %s, true)", (ctx["tenant_id"],))
        if ctx["principal_id"]:
            self.conn.execute("SELECT set_config('arbiter.principal_id', %s, true)", (ctx["principal_id"],))
        if ctx["request_id"]:
            self.conn.execute("SELECT set_config('arbiter.request_id', %s, true)", (ctx["request_id"],))
        return self

    def __exit__(self, exc_type, exc, tb):
        if self.conn is None: return False
        try:
            self.conn.rollback() if exc_type else self.conn.commit()
        finally:
            self.conn.close(); self.conn = None
        return False

    def execute(self, sql: str, args: Any = None):
        if self.conn is None: raise RuntimeError("database connection is not open")
        return self.conn.execute(_qmark_to_pyformat(sql), tuple(args or ()))

    def executescript(self, script: str):
        for statement in _split_sql_script(script):
            self.execute(_postgres_ddl(statement))
        return self


# ---- tenant RLS --------------------------------------------------------------
TENANT_SCOPED_TABLES = (
    "contract_versions", "authority_versions", "evidence_records", "resolution_runs", "audit_events",
    "work_item_state", "analysis_cases", "analysis_case_runs", "contract_templates",
    "principal_registry", "approval_requests", "approval_decisions", "settlement_packets",
    "evidence_monitors", "evidence_poll_runs", "evidence_exceptions", "resolution_reevaluation_requests",
    "operation_idempotency", "durable_jobs", "webhook_deliveries", "policy_drafts", "model_invocations",
    "secret_records", "model_provider_configs",
    # v0.19+ tenant-scoped operational and assurance resources.
    "reference_markets", "reference_accounts", "reference_positions", "reference_orders", "reference_trades",
    "operations_incidents", "recovery_drills", "assurance_runs", "holdout_datasets",
    "resilience_runs", "external_assurance_artifacts", "shadow_pilots", "shadow_contracts",
)


def rls_policy_sql(table: str) -> list[str]:
    if table not in TENANT_SCOPED_TABLES:
        raise ValueError("table is not approved for tenant RLS")
    policy = f"arbiter_tenant_{table}"
    return [
        f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS tenant_id TEXT",
        f"ALTER TABLE {table} ALTER COLUMN tenant_id SET DEFAULT current_setting('arbiter.tenant_id', true)",
        f"CREATE INDEX IF NOT EXISTS ix_{table}_tenant ON {table}(tenant_id)",
        f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY",
        f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY",
        f"DROP POLICY IF EXISTS {policy} ON {table}",
        f"CREATE POLICY {policy} ON {table} USING (tenant_id = current_setting('arbiter.tenant_id', true)) WITH CHECK (tenant_id = current_setting('arbiter.tenant_id', true))",
    ]


def apply_postgres_rls(db) -> dict[str, Any]:
    """Apply tenant columns/RLS after all service tables exist.

    Existing pre-v0.17 rows require an explicit ARBITER_MIGRATION_DEFAULT_TENANT.
    This intentionally fails closed rather than silently assigning ownership.
    """
    default_tenant = os.environ.get("ARBITER_MIGRATION_DEFAULT_TENANT", "").strip()
    applied: list[str] = []
    for table in TENANT_SCOPED_TABLES:
        exists = db.execute("SELECT to_regclass(?) AS name", (table,)).fetchone()
        if not exists or not exists.get("name"):
            continue
        db.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS tenant_id TEXT")
        nulls = db.execute(f"SELECT COUNT(*) AS n FROM {table} WHERE tenant_id IS NULL").fetchone()
        if int(nulls["n"]) > 0:
            if not default_tenant:
                raise RuntimeError(f"{table} has pre-v0.17 rows without tenant ownership; set ARBITER_MIGRATION_DEFAULT_TENANT explicitly")
            db.execute(f"UPDATE {table} SET tenant_id=? WHERE tenant_id IS NULL", (default_tenant,))
        db.execute(f"ALTER TABLE {table} ALTER COLUMN tenant_id SET NOT NULL")
        for statement in rls_policy_sql(table)[1:]:
            db.execute(statement)
        applied.append(table)
    db.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations (migration_id TEXT PRIMARY KEY, applied_at TEXT NOT NULL, checksum TEXT NOT NULL, description TEXT NOT NULL)"
    )
    db.execute(
        "INSERT INTO schema_migrations(migration_id,applied_at,checksum,description) VALUES(?,?,?,?) ON CONFLICT(migration_id) DO NOTHING",
        ("v0.17-production-data-plane", datetime.now(timezone.utc).isoformat(), hashlib.sha256("|".join(applied).encode()).hexdigest(), "production data plane tenant RLS and durability controls"),
    )
    return {"rls_tables": applied, "count": len(applied)}


# ---- content-addressed object storage ----------------------------------------
def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class LocalObjectStore:
    def __init__(self, root: str):
        self.root = Path(root); self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, digest: str) -> Path:
        return self.root / "sha256" / digest[:2] / digest

    def put_bytes(self, data: bytes, *, content_type: str = "application/octet-stream", metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        digest = _sha256(data); path = self._path(digest); path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            fd, tmp = tempfile.mkstemp(prefix=".arbiter-object-", dir=str(path.parent))
            try:
                with os.fdopen(fd, "wb") as f: f.write(data); f.flush(); os.fsync(f.fileno())
                os.replace(tmp, path)
            finally:
                if os.path.exists(tmp): os.unlink(tmp)
        return {"backend":"local","algorithm":"sha256","digest":digest,"object_key":f"sha256/{digest[:2]}/{digest}","size_bytes":len(data),"content_type":content_type,"metadata":metadata or {}}

    def get_bytes(self, digest: str) -> bytes:
        return self._path(digest).read_bytes()

    def exists(self, digest: str) -> bool:
        return self._path(digest).exists()


class S3ObjectStore:
    def __init__(self, bucket: str, prefix: str, kms_key_id: str = ""):
        try: import boto3
        except ImportError as e: raise RuntimeError("s3 object store selected but boto3 is not installed") from e
        self.bucket=bucket; self.prefix=prefix.strip("/"); self.kms_key_id=kms_key_id; self.client=boto3.client("s3")

    def _key(self, digest: str) -> str:
        tail=f"objects/sha256/{digest[:2]}/{digest}"
        return f"{self.prefix}/{tail}" if self.prefix else tail

    def put_bytes(self, data: bytes, *, content_type: str = "application/octet-stream", metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        digest=_sha256(data); key=self._key(digest)
        kwargs={"Bucket":self.bucket,"Key":key,"Body":data,"ContentType":content_type,"Metadata":{"sha256":digest}}
        if self.kms_key_id:
            kwargs.update(ServerSideEncryption="aws:kms", SSEKMSKeyId=self.kms_key_id)
        else:
            kwargs.update(ServerSideEncryption="AES256")
        self.client.put_object(**kwargs)
        return {"backend":"s3","algorithm":"sha256","digest":digest,"object_key":key,"bucket":self.bucket,"size_bytes":len(data),"content_type":content_type,"metadata":metadata or {}}

    def get_bytes(self, digest: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket,Key=self._key(digest))["Body"].read()

    def exists(self, digest: str) -> bool:
        try: self.client.head_object(Bucket=self.bucket,Key=self._key(digest)); return True
        except Exception: return False


def object_store():
    cfg=load_config()
    if cfg.object_store_backend == "s3": return S3ObjectStore(cfg.s3_bucket,cfg.s3_prefix,cfg.s3_kms_key_id)
    return LocalObjectStore(cfg.object_store_root)


# ---- concurrency --------------------------------------------------------------
_LOCKS: dict[str, threading.RLock] = {}; _LOCKS_GUARD=threading.Lock()


def _local_lock(key: str) -> threading.RLock:
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(key, threading.RLock())


@contextlib.contextmanager
def serialized(store, key: str) -> Iterator[None]:
    """Serialize a critical section.

    PostgreSQL uses a transaction-scoped advisory lock. SQLite uses a process lock;
    the database itself still supplies WAL/transaction durability for local development.
    """
    cfg=load_config()
    if cfg.database_backend == "postgresql":
        with store.connect() as db:
            db.execute("SELECT pg_advisory_xact_lock(hashtext(?))", (key,))
            yield
    else:
        lock=_local_lock(key)
        with lock: yield


# ---- service / backup posture -------------------------------------------------
class DataPlaneService:
    def __init__(self, store): self.store=store

    def initialize(self) -> dict[str, Any]:
        cfg=load_config()
        if cfg.database_backend == "postgresql":
            with self.store.connect() as db:
                result=apply_postgres_rls(db)
            return {"database":"postgresql", **result}
        Path(cfg.object_store_root).mkdir(parents=True, exist_ok=True)
        Path(cfg.backup_dir).mkdir(parents=True, exist_ok=True)
        return {"database":"sqlite","rls_tables":[],"count":0}

    def put_json_object(self, value: Any, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        raw=json.dumps(value,sort_keys=True,separators=(",",":"),default=str).encode("utf-8")
        return object_store().put_bytes(raw, content_type="application/json", metadata=metadata)

    def verify_object(self, ref: dict[str, Any]) -> dict[str, Any]:
        digest=str(ref.get("digest") or ""); data=object_store().get_bytes(digest); actual=_sha256(data)
        return {"ok":actual==digest,"digest":digest,"actual_digest":actual,"size_bytes":len(data)}

    def create_sqlite_backup(self, actor: str = "system:backup") -> dict[str, Any]:
        cfg=load_config()
        if cfg.database_backend != "sqlite": raise RuntimeError("in-process backup is only for the local SQLite reference backend")
        source=Path(self.store.path); Path(cfg.backup_dir).mkdir(parents=True,exist_ok=True)
        stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        dest=Path(cfg.backup_dir)/f"arbiter-{stamp}.db"
        src=sqlite3.connect(str(source)); dst=sqlite3.connect(str(dest))
        try: src.backup(dst)
        finally: dst.close(); src.close()
        digest=_sha256(dest.read_bytes())
        manifest={"schema":"arbiter.backup-manifest.v1","created_at":datetime.now(timezone.utc).isoformat(),"actor":actor,"database_backend":"sqlite","backup_file":dest.name,"sha256":digest,"size_bytes":dest.stat().st_size}
        manifest_path=dest.with_suffix(".manifest.json"); manifest_path.write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n")
        return {**manifest,"manifest_file":manifest_path.name}

    def verify_sqlite_backup(self, manifest_file: str) -> dict[str, Any]:
        cfg=load_config(); mp=Path(cfg.backup_dir)/manifest_file; manifest=json.loads(mp.read_text())
        bp=Path(cfg.backup_dir)/manifest["backup_file"]; actual=_sha256(bp.read_bytes())
        # sqlite integrity_check proves the copied DB can be opened and parsed.
        con=sqlite3.connect(str(bp))
        try: integrity=con.execute("PRAGMA integrity_check").fetchone()[0]
        finally: con.close()
        return {"ok":actual==manifest["sha256"] and integrity=="ok","sha256_ok":actual==manifest["sha256"],"sqlite_integrity":integrity,"backup_file":manifest["backup_file"]}

    def postgres_backup_plan(self) -> dict[str, Any]:
        cfg=load_config()
        return {
            "database_backend":"postgresql",
            "strategy":"managed snapshots + PITR + encrypted logical export for recovery drills",
            "requirements":["automated snapshots","point-in-time recovery","cross-zone durability","restore into isolated environment","checksum/application smoke test after restore"],
            "pg_dump_available":shutil.which("pg_dump") is not None,
            "pg_restore_available":shutil.which("pg_restore") is not None,
            "database_url_configured":bool(cfg.database_url),
        }

    def self_test(self) -> dict[str, Any]:
        # Cost-free/local deterministic path: object CAS + SQL translator + context + RLS SQL shape.
        probe={"kind":"arbiter-v0.17-self-test","ts":"fixed-for-hash","value":17}
        ref=self.put_json_object(probe,{"purpose":"self-test"}); verify=self.verify_object(ref)
        translated=_qmark_to_pyformat("SELECT '?' AS literal, value FROM t WHERE a=? AND b=?")
        policy=rls_policy_sql("analysis_cases")
        ctx_before=current_context(); tokens=bind_context("tenant-self-test","principal-self-test","request-self-test")
        try: ctx_during=current_context()
        finally: reset_context(tokens)
        return {
            "status":"completed",
            "object_store":{"ref":ref,"verification":verify},
            "sql_translation":{"sql":translated,"ok":translated.count("%s")==2 and "'?'" in translated},
            "rls":{"table":"analysis_cases","statements":policy,"force_rls":any("FORCE ROW LEVEL SECURITY" in x for x in policy),"with_check":any("WITH CHECK" in x for x in policy)},
            "context":{"before":ctx_before,"during":ctx_during,"after":current_context()},
            "authority":{"binding":False,"settlement_authority":False},
        }

    def posture(self) -> dict[str, Any]:
        cfg=load_config(); findings=configuration_findings(); ctx=current_context()
        return {
            "version":"0.17.0",
            "database":{
                "backend":cfg.database_backend,
                "production_required_backend":"postgresql",
                "database_url_configured":bool(cfg.database_url),
                "driver_ready":driver_available("psycopg") if cfg.database_backend=="postgresql" else True,
                "tls_mode":cfg.database_sslmode if cfg.database_backend=="postgresql" else None,
                "transaction_model":"database transactions + PostgreSQL advisory locks for critical sections",
            },
            "tenant_isolation":{
                "request_context":ctx,
                "postgres_rls":True,
                "force_rls":True,
                "tenant_scoped_table_count":len(TENANT_SCOPED_TABLES),
                "global_object_ids":True,
            },
            "object_storage":{
                "backend":cfg.object_store_backend,
                "content_addressed":True,
                "algorithm":"sha256",
                "bucket_configured":bool(cfg.s3_bucket) if cfg.object_store_backend=="s3" else None,
                "encryption":"SSE-KMS" if cfg.s3_kms_key_id else ("SSE-S3" if cfg.object_store_backend=="s3" else "filesystem/local-dev"),
            },
            "backup_restore": self.postgres_backup_plan() if cfg.database_backend=="postgresql" else {"strategy":"SQLite online backup + SHA-256 manifest + integrity_check","backup_dir":cfg.backup_dir},
            "configuration_findings":findings,
            "configuration_gate":"BLOCK" if any(x["severity"]=="BLOCK" for x in findings) else "PASS",
            "boundary":"v0.17 implements the production data-plane adapter, RLS policy machinery, immutable evidence object storage, concurrency primitives, and backup/restore verification hooks. Live certification still requires provisioned managed services and external operational/security validation.",
        }


_SERVICE=None

def get_service(store):
    global _SERVICE
    if _SERVICE is None or _SERVICE.store is not store: _SERVICE=DataPlaneService(store)
    return _SERVICE


def open_database_connection(sqlite_path: str):
    cfg=load_config()
    if cfg.database_backend == "postgresql":
        if not cfg.database_url: raise RuntimeError("ARBITER_DATABASE_URL is required for PostgreSQL")
        return PostgresConnection(cfg.database_url,cfg.database_sslmode)
    os.makedirs(os.path.dirname(sqlite_path),exist_ok=True)
    conn=sqlite3.connect(sqlite_path, timeout=30)
    conn.row_factory=sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn
