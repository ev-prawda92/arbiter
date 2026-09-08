"""Backward-compatible advisory LLM facade.

v0.16 routes model usage through model_gateway.py so every invocation is governed,
versioned, auditable, and explicitly non-binding.
"""
from __future__ import annotations

from .model_gateway import get_service, load_config
from .resolution_infra import store


def available() -> bool:
    cfg = load_config()
    return (cfg.provider == "openai" and bool(cfg.openai_api_key)) or (cfg.provider == "anthropic" and bool(cfg.anthropic_api_key))


def triage(question: str, criteria: str, *, tenant_id: str = "local", principal_id: str = "local:developer", actor: str = "operator:model-triage") -> dict:
    if not available():
        return {
            "error": "no_model_provider",
            "message": "Model triage is off. Configure OPENAI_API_KEY (preferred) or ANTHROPIC_API_KEY. Arbiter's binding rule engine continues to operate without a model.",
            "authority": {"binding": False, "role": "ADVISORY", "settlement_authority": False},
        }
    return get_service(store).invoke(
        "contract_triage", {"question": question, "criteria": criteria},
        tenant_id=tenant_id, principal_id=principal_id, actor=actor, model_tier="fast",
    )
