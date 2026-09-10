from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from . import compiler, developer, enterprise, identity_tenant, policy
from .real_benchmark.resolver import resolve_from_compiled_spec
from .resolution_infra import canonical_hash, gen_id, store as resolution_store, utcnow
from . import reliability

router = APIRouter(prefix="/v1", tags=["Arbiter v1"])


class CompileRequest(BaseModel):
    contract_id: str
    title: str
    rules: str
    contract_version: int = 1
    exchange_profile: str = "generic"
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvidenceInput(BaseModel):
    observed_value: Any = None
    observed_label: Any = None
    unit: str | None = None
    authority: str | None = None
    source_url: str | None = None
    retrieved_at: str | None = None
    raw_sha256: str | None = None


class ResolveRequest(CompileRequest):
    evidence: EvidenceInput | None = None


class VerifyRequest(BaseModel):
    resolution_id: str
    expected_response_sha256: str | None = None


class PublicResolutionStore:
    def __init__(self) -> None:
        self.init_db()

    def init_db(self) -> None:
        with resolution_store.connect() as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS public_api_resolutions (
                    resolution_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    contract_id TEXT NOT NULL,
                    request_sha256 TEXT NOT NULL,
                    response_sha256 TEXT NOT NULL,
                    request_json TEXT NOT NULL,
                    response_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            db.execute("CREATE INDEX IF NOT EXISTS ix_public_resolution_tenant ON public_api_resolutions(tenant_id, created_at)")

    def save(self, tenant_id: str, request: dict[str, Any], response: dict[str, Any], actor: str) -> dict[str, Any]:
        resolution_id = str(response["resolution_id"])
        request_sha = canonical_hash(request)
        response_sha = canonical_hash(response)
        now = utcnow()
        with resolution_store.connect() as db:
            db.execute(
                "INSERT INTO public_api_resolutions(resolution_id,tenant_id,contract_id,request_sha256,response_sha256,request_json,response_json,created_at) VALUES(?,?,?,?,?,?,?,?)",
                (resolution_id, tenant_id, request["contract_id"], request_sha, response_sha,
                 json.dumps(request, sort_keys=True, default=str), json.dumps(response, sort_keys=True, default=str), now),
            )
        resolution_store._audit(actor, "public_api.resolution.created", "public_api_resolution", resolution_id,
                                {"tenant_id": tenant_id, "contract_id": request["contract_id"], "response_sha256": response_sha})
        return {"request_sha256": request_sha, "response_sha256": response_sha, "created_at": now}

    def get(self, tenant_id: str, resolution_id: str) -> dict[str, Any] | None:
        with resolution_store.connect() as db:
            row = db.execute(
                "SELECT * FROM public_api_resolutions WHERE resolution_id=? AND tenant_id=?",
                (resolution_id, tenant_id),
            ).fetchone()
        if not row:
            return None
        d = dict(row)
        d["request"] = json.loads(d.pop("request_json"))
        d["response"] = json.loads(d.pop("response_json"))
        return d


_public_store = PublicResolutionStore()


def _principal(auth: dict[str, Any]):
    return identity_tenant.principal_from_auth(auth, production=enterprise.load_runtime_config().production)


def _compile(inp: CompileRequest) -> dict[str, Any]:
    return compiler.compile_rules(
        contract_id=inp.contract_id,
        contract_version=inp.contract_version,
        title=inp.title,
        rules=inp.rules,
        known_authorities=resolution_store.list_authorities(),
        metadata={**inp.metadata, "exchange_profile": inp.exchange_profile},
    )


@router.post("/contracts/compile")
def compile_contract_v1(inp: CompileRequest, auth=Depends(developer.require_scope("contracts:write"))):
    compiled = _compile(inp)
    return {
        "api_version": "v1",
        "contract_id": inp.contract_id,
        "governance_status": compiled.get("status"),
        "compilation": compiled,
        "compilation_sha256": canonical_hash(compiled),
    }


@router.post("/contracts/resolve")
def resolve_contract_v1(
    inp: ResolveRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    auth=Depends(developer.require_scope("resolution:write")),
):
    principal = _principal(auth)
    request_payload = inp.model_dump()
    idem = reliability.get_service(resolution_store)
    if idempotency_key:
        try:
            replay = idem.idempotency_get(idempotency_key, "v1.contracts.resolve", request_payload)
        except ValueError as e:
            raise HTTPException(409, str(e)) from e
        if replay:
            return replay["response"]

    compiled = _compile(inp)
    evidence = inp.evidence.model_dump() if inp.evidence else None
    resolved = resolve_from_compiled_spec(compiled, evidence)
    resolution_id = gen_id("vres")
    response = {
        "api_version": "v1",
        "resolution_id": resolution_id,
        "contract_id": inp.contract_id,
        "verdict": resolved.get("predicted_outcome", "HOLD"),
        "governance_status": compiled.get("status", "UNKNOWN"),
        "evidence_status": "SUFFICIENT" if evidence and resolved.get("predicted_outcome") in {"YES", "NO"} else "INSUFFICIENT",
        "requires_human_review": resolved.get("predicted_outcome") == "HOLD" or compiled.get("status") != "READY",
        "resolution_method": resolved.get("resolution_method"),
        "reason": resolved.get("reason"),
        "compiled_spec_sha256": canonical_hash(compiled.get("proposed_spec") or {}),
        "evidence_sha256": canonical_hash(evidence) if evidence else None,
        "policy_version": policy.load_policy().get("version"),
        "created_at": utcnow(),
    }
    integrity = _public_store.save(principal.tenant_id, request_payload, response, principal.principal_id)
    response["response_sha256"] = canonical_hash(response)
    response["request_sha256"] = integrity["request_sha256"]

    if idempotency_key:
        idem.idempotency_put(idempotency_key, "v1.contracts.resolve", request_payload, response)
    return response


@router.get("/resolutions/{resolution_id}")
def get_resolution_v1(resolution_id: str, auth=Depends(developer.require_api_key)):
    principal = _principal(auth)
    row = _public_store.get(principal.tenant_id, resolution_id)
    if not row:
        raise HTTPException(404, "resolution not found")
    return {
        "api_version": "v1",
        "resolution_id": resolution_id,
        "response": row["response"],
        "request_sha256": row["request_sha256"],
        "response_sha256": row["response_sha256"],
        "created_at": row["created_at"],
    }


@router.post("/contracts/verify")
def verify_resolution_v1(inp: VerifyRequest, auth=Depends(developer.require_api_key)):
    principal = _principal(auth)
    row = _public_store.get(principal.tenant_id, inp.resolution_id)
    if not row:
        raise HTTPException(404, "resolution not found")
    actual = row["response_sha256"]
    matches = inp.expected_response_sha256 in (None, actual)
    return {
        "api_version": "v1",
        "resolution_id": inp.resolution_id,
        "verified": matches,
        "response_sha256": actual,
        "expected_response_sha256": inp.expected_response_sha256,
    }


@router.get("/audit/{resolution_id}")
def resolution_audit_v1(resolution_id: str, auth=Depends(developer.require_api_key)):
    principal = _principal(auth)
    row = _public_store.get(principal.tenant_id, resolution_id)
    if not row:
        raise HTTPException(404, "resolution not found")
    return {
        "api_version": "v1",
        "resolution_id": resolution_id,
        "chain": resolution_store.verify_audit_chain(),
        "events": resolution_store.audit_log(limit=100, object_type="public_api_resolution", object_id=resolution_id),
        "request_sha256": row["request_sha256"],
        "response_sha256": row["response_sha256"],
    }
