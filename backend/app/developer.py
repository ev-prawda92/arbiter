"""Developer-platform metadata and enterprise API-key authorization for Arbiter."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from typing import Callable

from fastapi import Header, HTTPException

from . import identity_federation

from .enterprise import load_runtime_config

ALL_SCOPES = {
    "contracts:write", "cases:write", "policy:write", "authorities:write",
    "evidence:write", "resolution:write", "operations:write", "approvals:write", "settlement:authorize", "benchmark:run", "ai:use", "ai:read", "admin:*",
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
                "tenant_id": record.get("tenant_id"),
                "principal_id": record.get("principal_id"),
                "principal_type": record.get("principal_type"),
            }
    cfg = load_runtime_config()
    if cfg.allow_legacy_keys:
        for legacy in configured_api_keys():
            if hmac.compare_digest(key, legacy):
                return {"authenticated": True, "mode": "legacy-api-key", "key_id": digest[:12], "scopes": ["admin:*"], "tenant_id": "local", "principal_id": "legacy:"+digest[:12], "principal_type": "service"}
    return None


def authenticate(x_arbiter_key: str | None = None, authorization: str | None = None) -> dict:
    cfg = load_runtime_config()
    enabled = api_auth_enabled() or identity_federation.load_config().enabled
    if authorization and authorization.lower().startswith("bearer "):
        try:
            return identity_federation.authenticate_bearer(authorization.split(" ", 1)[1].strip())
        except Exception as exc:
            raise HTTPException(status_code=401, detail=f"invalid bearer token: {exc}") from exc
    if not enabled and not cfg.require_auth:
        return {"authenticated": False, "mode": "local-open", "key_id": None, "scopes": ["admin:*"], "tenant_id": "local", "principal_id": "local:developer", "principal_type": "human"}
    if not x_arbiter_key:
        raise HTTPException(status_code=401, detail="missing authentication credential")
    auth = _match_key(x_arbiter_key)
    if not auth:
        raise HTTPException(status_code=401, detail="invalid X-Arbiter-Key")
    return auth


def require_api_key(x_arbiter_key: str | None = Header(default=None, alias="X-Arbiter-Key"), authorization: str | None = Header(default=None, alias="Authorization")) -> dict:
    return authenticate(x_arbiter_key, authorization)


def require_scope(scope: str) -> Callable:
    def dependency(x_arbiter_key: str | None = Header(default=None, alias="X-Arbiter-Key"), authorization: str | None = Header(default=None, alias="Authorization")) -> dict:
        auth = authenticate(x_arbiter_key, authorization)
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
        "product_version": "0.26.0",
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
        "core_resources": ["semantic-contract-intelligence", "contracts", "authorities", "evidence", "evidence-monitors", "source-health", "evidence-exceptions", "resolution-reevaluations", "resolution-runs", "approvals", "settlement-packets", "policy-drafts", "work-queue", "portfolio", "audit", "model-gateway", "model-invocations", "case-copilot", "data-plane", "enterprise-secrets", "model-providers", "oidc-federation", "reference-exchange", "reference-orders", "operations-resilience", "incidents", "recovery-drills", "settlement-assurance", "holdout-datasets", "deployment-readiness", "resilience-lab", "external-assurance", "shadow-pilots"],
        "compiler": {"endpoint": "/api/compile", "version": "0.1.3"},
        "semantic_contract_intelligence": {"endpoint": "/api/semantic-analyze", "version": "0.13.0", "gate_mode": "advisory"},
        "enterprise_identity": {"version": "0.14.0", "tenant_context": "principal-bound", "principal_types": ["human", "service"]},
        "production_reliability": {"version": "0.15.0", "durable_jobs": True, "idempotency": True, "signed_webhook_envelopes": True, "replay_protection": True},
        "model_intelligence_gateway": {"version": "0.16.0", "provider_abstraction": True, "structured_outputs": True, "prompt_versioning": True, "audit_logging": True, "settlement_authority": False},
        "production_data_plane": {"version": "0.17.0", "postgresql_adapter": True, "tenant_rls": True, "content_addressed_evidence_objects": True, "backup_restore_hooks": True, "settlement_authority": False},
        "enterprise_secrets": {"version": "0.18.0", "tenant_provider_credentials": True, "write_only_secret_api": True, "production_backend": "aws-secrets-manager+kms", "settlement_authority": False},
        "identity_federation": {"version": "0.18.0", "oidc_bearer": True, "api_key_fallback": True},
        "reference_exchange": {"version": "0.26.0", "play_money_only": True, "end_to_end_settlement_harness": True, "sandbox_matching_engine": True, "real_money_custody": False},
        "operations_resilience": {"version": "0.20.0", "dependency_health": True, "backpressure": True, "incident_lifecycle": True, "recovery_drills": True, "external_observability_required": True},
        "settlement_assurance": {"version": "0.21.0", "internal_adversarial_suite": True, "frozen_holdout_registry": True, "production_settlement_certified": False, "independent_review_required": True},
        "deployment_readiness": {"version": "0.22.0", "aws_reference_iac": True, "deployment_proven": False},
        "resilience_lab": {"version": "0.23.0", "local_failure_scenarios": True, "external_evidence_registry": True},
        "external_assurance": {"version": "0.24.0", "independent_evidence_registry": True, "production_settlement_certified": False},
        "shadow_pilot": {"version": "0.25.0", "mode": "shadow-only", "settlement_authority": False},
        "webhook_event_catalog": WEBHOOK_EVENTS,
        "stability": "preview — endpoint contracts may evolve before v1.0",
    }
