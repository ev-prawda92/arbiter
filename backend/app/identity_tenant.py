"""Arbiter v0.14 enterprise identity and tenant boundary.

Provides a dependency-light reference implementation for organization tenancy,
service identities, and request-context enforcement. Local development defaults
remain simple; production configurations fail closed when authenticated principals
lack tenant or principal metadata.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from .resolution_infra import utcnow, gen_id


@dataclass(frozen=True)
class Principal:
    principal_id: str
    principal_type: str
    tenant_id: str
    scopes: tuple[str, ...]
    auth_mode: str
    key_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "principal_id": self.principal_id,
            "principal_type": self.principal_type,
            "tenant_id": self.tenant_id,
            "scopes": list(self.scopes),
            "auth_mode": self.auth_mode,
            "key_id": self.key_id,
        }


class TenantRegistry:
    def __init__(self, store):
        self.store = store
        self.init_db()

    def init_db(self) -> None:
        with self.store.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS tenants (
                    tenant_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS principal_registry (
                    principal_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    principal_type TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
                );
                CREATE INDEX IF NOT EXISTS ix_principal_tenant ON principal_registry(tenant_id,status);
                """
            )

    def ensure_local(self) -> None:
        # Local bootstrap data must never be silently created in a production tenant registry.
        if os.environ.get("ARBITER_ENV", "development").strip().lower() in {"prod", "production"}:
            return
        with self.store.connect() as db:
            row = db.execute("SELECT tenant_id FROM tenants WHERE tenant_id='local'").fetchone()
            if not row:
                db.execute(
                    "INSERT INTO tenants(tenant_id,name,status,created_at,created_by,metadata_json) VALUES(?,?,?,?,?,?)",
                    ("local", "Local Development", "active", utcnow(), "system:seed", json.dumps({"environment": "development"})),
                )

    def create_tenant(self, name: str, actor: str, tenant_id: str | None = None, metadata: dict | None = None) -> dict:
        tenant_id = tenant_id or gen_id("tenant")
        now = utcnow()
        with self.store.connect() as db:
            if db.execute("SELECT 1 FROM tenants WHERE tenant_id=?", (tenant_id,)).fetchone():
                raise ValueError("tenant already exists")
            db.execute(
                "INSERT INTO tenants(tenant_id,name,status,created_at,created_by,metadata_json) VALUES(?,?,?,?,?,?)",
                (tenant_id, name, "active", now, actor, json.dumps(metadata or {}, sort_keys=True)),
            )
        self.store._audit(actor, "tenant.created", "tenant", tenant_id, {"name": name})
        return self.get_tenant(tenant_id)

    def get_tenant(self, tenant_id: str) -> dict | None:
        with self.store.connect() as db:
            r = db.execute("SELECT * FROM tenants WHERE tenant_id=?", (tenant_id,)).fetchone()
        if not r:
            return None
        out = dict(r); out["metadata"] = json.loads(out.pop("metadata_json")); return out

    def list_tenants(self) -> list[dict]:
        with self.store.connect() as db:
            rows = db.execute("SELECT * FROM tenants ORDER BY created_at").fetchall()
        out=[]
        for r in rows:
            d=dict(r); d["metadata"]=json.loads(d.pop("metadata_json")); out.append(d)
        return out

    def register_principal(self, principal_id: str, tenant_id: str, principal_type: str, display_name: str, actor: str, metadata: dict | None = None) -> dict:
        if principal_type not in {"human", "service"}:
            raise ValueError("principal_type must be human or service")
        if not self.get_tenant(tenant_id):
            raise ValueError("unknown tenant")
        now=utcnow()
        with self.store.connect() as db:
            if db.execute("SELECT 1 FROM principal_registry WHERE principal_id=?", (principal_id,)).fetchone():
                raise ValueError("principal already exists")
            db.execute(
                "INSERT INTO principal_registry(principal_id,tenant_id,principal_type,display_name,status,created_at,created_by,metadata_json) VALUES(?,?,?,?,?,?,?,?)",
                (principal_id,tenant_id,principal_type,display_name,"active",now,actor,json.dumps(metadata or {},sort_keys=True)),
            )
        self.store._audit(actor,"principal.registered","principal",principal_id,{"tenant_id":tenant_id,"principal_type":principal_type})
        return self.get_principal(principal_id)

    def get_principal(self, principal_id: str) -> dict | None:
        with self.store.connect() as db:
            r=db.execute("SELECT * FROM principal_registry WHERE principal_id=?",(principal_id,)).fetchone()
        if not r: return None
        d=dict(r); d["metadata"]=json.loads(d.pop("metadata_json")); return d

    def list_principals(self, tenant_id: str | None = None) -> list[dict]:
        with self.store.connect() as db:
            if tenant_id:
                rows=db.execute("SELECT * FROM principal_registry WHERE tenant_id=? ORDER BY created_at",(tenant_id,)).fetchall()
            else:
                rows=db.execute("SELECT * FROM principal_registry ORDER BY created_at").fetchall()
        out=[]
        for r in rows:
            d=dict(r); d["metadata"]=json.loads(d.pop("metadata_json")); out.append(d)
        return out


def principal_from_auth(auth: dict, production: bool = False) -> Principal:
    """Normalize developer.authenticate() output into an enterprise principal."""
    mode = str(auth.get("mode") or "unknown")
    scopes = tuple(auth.get("scopes") or ())
    principal_id = str(auth.get("principal_id") or "")
    principal_type = str(auth.get("principal_type") or "")
    tenant_id = str(auth.get("tenant_id") or "")
    if mode == "local-open" and not production:
        principal_id = principal_id or "local:developer"
        principal_type = principal_type or "human"
        tenant_id = tenant_id or "local"
    if production:
        missing=[k for k,v in {"principal_id":principal_id,"principal_type":principal_type,"tenant_id":tenant_id}.items() if not v]
        if missing:
            raise ValueError("production principal missing: " + ", ".join(missing))
    return Principal(principal_id or "anonymous", principal_type or "unknown", tenant_id or "local", scopes, mode, auth.get("key_id"))


def validate_tenant_override(principal: Principal, requested_tenant: str | None) -> str:
    if not requested_tenant:
        return principal.tenant_id
    if requested_tenant != principal.tenant_id and "admin:*" not in principal.scopes:
        raise PermissionError("cross-tenant request forbidden")
    return requested_tenant


def posture(store, runtime_config, key_records: list[dict]) -> dict:
    registry=TenantRegistry(store); registry.ensure_local()
    malformed=[]
    for r in key_records:
        if not r.get("tenant_id") or not r.get("principal_id") or r.get("principal_type") not in {"human","service"}:
            malformed.append(str(r.get("id") or "unnamed"))
    findings=[]
    if runtime_config.production and malformed:
        findings.append({"severity":"BLOCK","code":"PRINCIPAL_METADATA_INCOMPLETE","detail":"Production API-key records must include tenant_id, principal_id, and principal_type.","key_ids":malformed})
    return {
        "tenant_boundary": "principal-bound tenant context",
        "principal_types": ["human","service"],
        "registered_tenants": len(registry.list_tenants()),
        "registered_principals": len(registry.list_principals()),
        "malformed_key_records": malformed,
        "findings": findings,
    }
