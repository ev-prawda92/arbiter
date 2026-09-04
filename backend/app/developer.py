"""Developer-platform metadata and enterprise API-key authorization for Arbiter."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from typing import Callable

from fastapi import Header, HTTPException

from .enterprise import load_runtime_config

ALL_SCOPES = {
    "contracts:write", "cases:write", "policy:write", "authorities:write",
    "evidence:write", "resolution:write", "operations:write", "approvals:write", "settlement:authorize", "benchmark:run", "admin:*",
}


def configured_api_keys() -> set[str]:
    raw = os.environ.get("ARBITER_API_KEYS", "")
    return {k.strip() for k in raw.split(",") if k.strip()}


def configured_key_records() -> list[dict]:
    """Load hashed key records from ARBITER_API_KEY_RECORDS.

    Format: JSON array of {"id":"ops","sha256":"...","scopes":["cases:write"]}.
    Secrets themselves never need to appear in the record.
    """
    raw = os.environ.get("ARBITER_API_KEY_RECORDS", "").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError("ARBITER_API_KEY_RECORDS must be valid JSON") from e
    if not isinstance(data, list):
        raise RuntimeError("ARBITER_API_KEY_RECORDS must be a JSON array")
    return [r for r in data if isinstance(r, dict)]


def api_auth_enabled() -> bool:
    cfg = load_runtime_config()
    return cfg.require_auth or bool(configured_api_keys()) or bool(configured_key_records())


def _match_key(key: str) -> dict | None:
    digest = hashlib.sha256(key.encode()).hexdigest()
    for record in configured_key_records():
        expected = str(record.get("sha256", ""))
        if expected and hmac.compare_digest(digest, expected):
            return {
                "authenticated": True,
                "mode": "hashed-api-key",
                "key_id": str(record.get("id") or digest[:12]),
                "scopes": list(record.get("scopes") or []),
            }
    cfg = load_runtime_config()
    if cfg.allow_legacy_keys:
        for legacy in configured_api_keys():
            if hmac.compare_digest(key, legacy):
                return {"authenticated": True, "mode": "legacy-api-key", "key_id": digest[:12], "scopes": ["admin:*"]}
    return None


def authenticate(x_arbiter_key: str | None = Header(default=None, alias="X-Arbiter-Key")) -> dict:
    cfg = load_runtime_config()
    enabled = api_auth_enabled()
    if not enabled and not cfg.require_auth:
        return {"authenticated": False, "mode": "local-open", "key_id": None, "scopes": ["admin:*"]}
    if not x_arbiter_key:
        raise HTTPException(status_code=401, detail="missing X-Arbiter-Key")
    auth = _match_key(x_arbiter_key)
    if not auth:
        raise HTTPException(status_code=401, detail="invalid X-Arbiter-Key")
    return auth


def require_api_key(x_arbiter_key: str | None = Header(default=None, alias="X-Arbiter-Key")) -> dict:
    return authenticate(x_arbiter_key)


def require_scope(scope: str) -> Callable:
    def dependency(x_arbiter_key: str | None = Header(default=None, alias="X-Arbiter-Key")) -> dict:
        auth = authenticate(x_arbiter_key)
        scopes = set(auth.get("scopes") or [])
        if "admin:*" not in scopes and scope not in scopes:
            raise HTTPException(status_code=403, detail=f"API key lacks required scope: {scope}")
        return auth
    return dependency


WEBHOOK_EVENTS = [
    "contract.created", "contract.blocked", "contract.review_required",
    "evidence.received", "evidence.revised", "evidence.conflict", "evidence.source_outage", "resolution.reevaluation_requested", "resolution.pending",
    "resolution.held", "resolution.completed", "approval.requested", "approval.approved", "settlement.packet.created", "control.failed",
    "work_item.updated", "audit.chain_failed",
]


def developer_manifest() -> dict:
    cfg = load_runtime_config()
    return {
        "api_version": "v1-preview",
        "product_version": "0.12.0",
        "auth": {
            "enabled": api_auth_enabled(),
            "required": cfg.require_auth,
            "header": "X-Arbiter-Key",
            "preferred_environment": "ARBITER_API_KEY_RECORDS",
            "legacy_environment": "ARBITER_API_KEYS",
            "scoped_authorization": True,
            "note": "Local development can remain open. Production defaults to fail-closed authentication.",
        },
        "docs": {"swagger": "/docs", "redoc": "/redoc", "openapi": "/openapi.json"},
        "core_resources": ["contracts", "authorities", "evidence", "evidence-monitors", "source-health", "evidence-exceptions", "resolution-reevaluations", "resolution-runs", "approvals", "settlement-packets", "policy-drafts", "work-queue", "portfolio", "audit"],
        "compiler": {"endpoint": "/api/compile", "version": "0.1.2"},
        "webhook_event_catalog": WEBHOOK_EVENTS,
        "stability": "preview — endpoint contracts may evolve before v1.0",
    }
