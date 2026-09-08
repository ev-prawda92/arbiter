"""Enterprise runtime controls for Arbiter.

This module is deliberately small and dependency-light so local development stays easy,
while production deployments can fail closed on unsafe configuration.
"""
from __future__ import annotations

import os
import secrets
from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeConfig:
    environment: str
    require_auth: bool
    cors_origins: tuple[str, ...]
    allow_legacy_keys: bool
    database_backend: str

    @property
    def production(self) -> bool:
        return self.environment in {"production", "prod"}


def _truthy(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def load_runtime_config() -> RuntimeConfig:
    environment = os.environ.get("ARBITER_ENV", "development").strip().lower()
    production = environment in {"production", "prod"}
    require_auth = _truthy(os.environ.get("ARBITER_REQUIRE_AUTH"), default=production)
    raw_origins = os.environ.get("ARBITER_CORS_ORIGINS", "")
    if raw_origins.strip():
        origins = tuple(o.strip() for o in raw_origins.split(",") if o.strip())
    else:
        origins = () if production else ("*",)
    allow_legacy_keys = _truthy(os.environ.get("ARBITER_ALLOW_LEGACY_KEYS"), default=not production)
    database_backend = os.environ.get("ARBITER_DATABASE_BACKEND", "sqlite").strip().lower()
    return RuntimeConfig(environment, require_auth, origins, allow_legacy_keys, database_backend)


def configuration_findings() -> list[dict]:
    cfg = load_runtime_config()
    findings: list[dict] = []
    if cfg.production and not cfg.require_auth:
        findings.append({"severity": "BLOCK", "code": "AUTH_DISABLED_IN_PRODUCTION", "detail": "Production must require authentication."})
    if cfg.production and "*" in cfg.cors_origins:
        findings.append({"severity": "BLOCK", "code": "WILDCARD_CORS_IN_PRODUCTION", "detail": "Production CORS origins must be explicitly allow-listed."})
    if cfg.production and cfg.allow_legacy_keys:
        findings.append({"severity": "WARN", "code": "LEGACY_KEYS_ENABLED", "detail": "Raw legacy API keys should be disabled in production; prefer hashed key records."})
    if cfg.production and cfg.database_backend != "postgresql":
        findings.append({"severity": "BLOCK", "code": "PRODUCTION_DATABASE_NOT_POSTGRESQL", "detail": "Production deployments must set ARBITER_DATABASE_BACKEND=postgresql and use the production data adapter."})
    if cfg.production and not os.environ.get("ARBITER_SETTLEMENT_SIGNING_SECRET"):
        findings.append({"severity": "BLOCK", "code": "SETTLEMENT_SIGNING_KEY_MISSING", "detail": "Production settlement authorization requires ARBITER_SETTLEMENT_SIGNING_SECRET (replace with KMS/HSM-backed asymmetric signing before live settlement)."})
    if cfg.production and not os.environ.get("ARBITER_WEBHOOK_SIGNING_SECRET"):
        findings.append({"severity": "BLOCK", "code": "WEBHOOK_SIGNING_KEY_MISSING", "detail": "Production outbound webhook envelopes require ARBITER_WEBHOOK_SIGNING_SECRET (replace with KMS/HSM-backed asymmetric signing before live settlement)."})
    return findings


def security_headers(request_id: str | None = None) -> dict[str, str]:
    return {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "no-referrer",
        "Cache-Control": "no-store",
        "X-Request-ID": request_id or secrets.token_hex(12),
    }


def posture() -> dict:
    cfg = load_runtime_config()
    findings = configuration_findings()
    return {
        "environment": cfg.environment,
        "production_mode": cfg.production,
        "authentication_required": cfg.require_auth,
        "cors_origins": list(cfg.cors_origins),
        "legacy_api_keys_allowed": cfg.allow_legacy_keys,
        "database_backend": cfg.database_backend,
        "configuration_findings": findings,
        "configuration_gate": "BLOCK" if any(f["severity"] == "BLOCK" for f in findings) else "PASS",
        "security_boundary": (
            "These are application-layer controls, not a certification. Production readiness also requires "
            "hardened infrastructure, secrets management, SSO/RBAC integration, vulnerability management, "
            "backup/restore validation, monitoring, incident response, and independent security testing."
        ),
    }
