"""Arbiter v0.18 OIDC federation foundation.

Supports enterprise bearer-token authentication alongside existing scoped API keys.
Production deployments must configure issuer, audience, and JWKS URL explicitly.
"""
from __future__ import annotations
import os
from dataclasses import dataclass
from typing import Any
import httpx

VERSION="0.18.0"

@dataclass(frozen=True)
class OIDCConfig:
    enabled: bool
    issuer: str
    audience: str
    jwks_url: str
    tenant_claim: str
    principal_claim: str
    scope_claim: str
    algorithms: tuple[str,...]


def load_config() -> OIDCConfig:
    issuer=os.environ.get("ARBITER_OIDC_ISSUER","").strip()
    audience=os.environ.get("ARBITER_OIDC_AUDIENCE","").strip()
    jwks=os.environ.get("ARBITER_OIDC_JWKS_URL","").strip()
    enabled=os.environ.get("ARBITER_OIDC_ENABLED","false").lower() in {"1","true","yes"} or bool(issuer and audience and jwks)
    return OIDCConfig(enabled,issuer,audience,jwks,os.environ.get("ARBITER_OIDC_TENANT_CLAIM","tenant_id"),os.environ.get("ARBITER_OIDC_PRINCIPAL_CLAIM","sub"),os.environ.get("ARBITER_OIDC_SCOPE_CLAIM","scope"),tuple(x.strip() for x in os.environ.get("ARBITER_OIDC_ALGORITHMS","RS256").split(",") if x.strip()))


def _scopes(claim: Any) -> list[str]:
    if isinstance(claim,str): return [x for x in claim.split() if x]
    if isinstance(claim,list): return [str(x) for x in claim]
    return []


def map_claims(claims: dict[str,Any], cfg: OIDCConfig | None=None) -> dict[str,Any]:
    cfg=cfg or load_config()
    principal=str(claims.get(cfg.principal_claim) or "").strip()
    tenant=str(claims.get(cfg.tenant_claim) or "").strip()
    if not principal or not tenant:
        raise ValueError("OIDC token missing principal or tenant claim")
    return {"authenticated":True,"mode":"oidc-bearer","key_id":None,"scopes":_scopes(claims.get(cfg.scope_claim)),"tenant_id":tenant,"principal_id":principal,"principal_type":"human"}


def authenticate_bearer(token: str) -> dict[str,Any]:
    cfg=load_config()
    if not cfg.enabled: raise ValueError("OIDC federation is not configured")
    if not (cfg.issuer and cfg.audience and cfg.jwks_url): raise ValueError("OIDC configuration incomplete")
    try:
        import jwt
        from jwt import PyJWKClient
    except ImportError as exc:
        raise RuntimeError("OIDC enabled but PyJWT is not installed") from exc
    key=PyJWKClient(cfg.jwks_url).get_signing_key_from_jwt(token).key
    claims=jwt.decode(token,key=key,algorithms=list(cfg.algorithms),audience=cfg.audience,issuer=cfg.issuer,options={"require":["exp","iat","iss","sub"]})
    return map_claims(claims,cfg)


def posture() -> dict[str,Any]:
    cfg=load_config(); production=os.environ.get("ARBITER_ENV","local").lower()=="production"; findings=[]
    if cfg.enabled and not (cfg.issuer and cfg.audience and cfg.jwks_url): findings.append({"severity":"BLOCK" if production else "WARN","code":"OIDC_CONFIG_INCOMPLETE","detail":"OIDC requires issuer, audience, and JWKS URL."})
    return {"version":VERSION,"enabled":cfg.enabled,"issuer":cfg.issuer or None,"audience":cfg.audience or None,"jwks_configured":bool(cfg.jwks_url),"tenant_claim":cfg.tenant_claim,"principal_claim":cfg.principal_claim,"scope_claim":cfg.scope_claim,"algorithms":list(cfg.algorithms),"findings":findings}


def self_test() -> dict[str,Any]:
    cfg=OIDCConfig(True,"https://issuer.example","arbiter","https://issuer.example/.well-known/jwks.json","tenant_id","sub","scope",("RS256",))
    mapped=map_claims({"sub":"user:test","tenant_id":"tenant:test","scope":"ai:read ai:use"},cfg)
    return {"ok":mapped["principal_id"]=="user:test" and mapped["tenant_id"]=="tenant:test" and "ai:use" in mapped["scopes"],"mapped":mapped,"signature_call_performed":False}
