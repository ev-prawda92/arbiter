"""Developer-platform metadata and optional API-key gate for Arbiter."""
from __future__ import annotations

import hashlib
import os
from typing import Iterable

from fastapi import Header, HTTPException


def configured_api_keys() -> set[str]:
    raw = os.environ.get("ARBITER_API_KEYS", "")
    return {k.strip() for k in raw.split(",") if k.strip()}


def api_auth_enabled() -> bool:
    return bool(configured_api_keys())


def require_api_key(x_arbiter_key: str | None = Header(default=None, alias="X-Arbiter-Key")) -> dict:
    keys = configured_api_keys()
    if not keys:
        return {"authenticated": False, "mode": "local-open"}
    if not x_arbiter_key or x_arbiter_key not in keys:
        raise HTTPException(status_code=401, detail="missing or invalid X-Arbiter-Key")
    kid = hashlib.sha256(x_arbiter_key.encode()).hexdigest()[:12]
    return {"authenticated": True, "mode": "api-key", "key_id": kid}


WEBHOOK_EVENTS = [
    "contract.created", "contract.blocked", "contract.review_required",
    "evidence.received", "evidence.revised", "resolution.pending",
    "resolution.held", "resolution.completed", "control.failed",
    "work_item.updated", "audit.chain_failed",
]


def developer_manifest() -> dict:
    return {
        "api_version": "v1-preview",
        "product_version": "0.9.0",
        "auth": {
            "enabled": api_auth_enabled(),
            "header": "X-Arbiter-Key",
            "environment": "ARBITER_API_KEYS",
            "note": "Local development is open when ARBITER_API_KEYS is unset.",
        },
        "docs": {"swagger": "/docs", "redoc": "/redoc", "openapi": "/openapi.json"},
        "core_resources": ["contracts", "authorities", "evidence", "resolution-runs", "work-queue", "portfolio", "audit"],
        "compiler": {"endpoint": "/api/compile", "version": "0.1.0"},
        "webhook_event_catalog": WEBHOOK_EVENTS,
        "stability": "preview — endpoint contracts may evolve before v1.0",
    }
