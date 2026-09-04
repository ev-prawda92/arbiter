"""
Arbiter API.

Endpoints
  GET  /api/health
  GET  /api/markets           -> scored docket (?live=true to try Kalshi)
  GET  /api/markets/{ticker}  -> single scored report + resolution trail
  GET  /api/monitoring        -> read-only platform intelligence
  GET  /api/policy            -> current adjudication policy + changelog
  POST /api/policy            -> governed policy update (logged)
  POST /api/analyze           -> score arbitrary pasted contract (rules + optional LLM triage)

Serves the frontend at /.
"""

import os
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import engine, feeds, monitoring, policy, llm, intelligence, evidence, executive, workflow, compiler, developer, enterprise, exchange_profiles, active_evidence
from .resolution_infra import (store as resolution_store, seed_reference_data, ResolutionSpecification, Authority, EvidenceRecord, ResolutionRun, gen_id, utcnow, canonical_hash)
from .control_library import CONTROLS, evaluate_spec, evaluate_evidence, evaluate_run
from .benchmark.runner import run as run_benchmark

app = FastAPI(
    title="Arbiter API",
    version="0.11.0",
    description=(
        "Resolution control infrastructure for event-contract exchanges. "
        "Design contracts, govern authorities, preserve evidence, execute version-pinned resolution runs, "
        "triage operator work, and verify the audit chain. Advisory intelligence is non-binding."
    ),
    docs_url="/docs", redoc_url="/redoc", openapi_url="/openapi.json",
    contact={"name": "Arbiter Developer Platform"},
)
runtime_config = enterprise.load_runtime_config()
app.add_middleware(CORSMiddleware, allow_origins=list(runtime_config.cors_origins), allow_methods=["GET", "POST", "OPTIONS"], allow_headers=["Content-Type", "X-Arbiter-Key", "Idempotency-Key", "X-Request-ID"])

@app.middleware("http")
async def enterprise_boundary(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or __import__("secrets").token_hex(12)
    # Fail closed on unsafe production configuration before serving control-plane APIs.
    findings = enterprise.configuration_findings()
    if request.url.path.startswith("/api/") and request.url.path not in {"/api/health", "/api/readiness", "/api/security-posture"}:
        if any(f["severity"] == "BLOCK" for f in findings):
            from fastapi.responses import JSONResponse
            return JSONResponse(status_code=503, content={"detail": "unsafe production configuration", "findings": findings}, headers=enterprise.security_headers(request_id))
        if enterprise.load_runtime_config().require_auth:
            try:
                developer.authenticate(request.headers.get("X-Arbiter-Key"))
            except HTTPException as e:
                from fastapi.responses import JSONResponse
                return JSONResponse(status_code=e.status_code, content={"detail": e.detail}, headers=enterprise.security_headers(request_id))
    response = await call_next(request)
    for k, v in enterprise.security_headers(request_id).items():
        response.headers[k] = v
    return response

_FRONTEND = os.path.join(os.path.dirname(__file__), "..", "dist")

# ---- simple in-process cache so repeated calls in a session are consistent ----
_CACHE = {"reports": None}


def _reports(live=False):
    markets = feeds.get_markets(live=live)
    pol = policy.load_policy()
    reports = [engine.analyze(m, pol) for m in markets]
    for m, r in zip(markets, reports):
        r["_source"] = m.get("_source", "sample")
    _CACHE["reports"] = reports
    return reports


@app.get("/api/developer", tags=["Developer"])
def developer_manifest():
    return developer.developer_manifest()


class CompileIn(BaseModel):
    contract_id: str
    title: str
    rules: str
    contract_version: int = 1
    metadata: dict = {}
    exchange_profile: str = "generic"
    actor: str = "exchange.market-ops"


@app.post("/api/compile", tags=["Compiler"])
def compile_contract(inp: CompileIn, auth=Depends(developer.require_scope("contracts:write"))):
    authorities = resolution_store.list_authorities()
    return compiler.compile_rules(
        contract_id=inp.contract_id,
        contract_version=inp.contract_version,
        title=inp.title,
        rules=inp.rules,
        known_authorities=authorities,
        metadata={**inp.metadata, "exchange_profile": inp.exchange_profile},
    )


@app.post("/api/compile-and-create", tags=["Compiler"])
def compile_and_create(inp: CompileIn, auth=Depends(developer.require_scope("contracts:write"))):
    authorities = resolution_store.list_authorities()
    compiled = compiler.compile_rules(
        contract_id=inp.contract_id,
        contract_version=inp.contract_version,
        title=inp.title,
        rules=inp.rules,
        known_authorities=authorities,
        metadata={**inp.metadata, "exchange_profile": inp.exchange_profile},
    )
    if compiled["status"] != "READY":
        raise HTTPException(422, {"error": "compilation_not_ready", "compilation": compiled})
    spec_data = dict(compiled["proposed_spec"])
    spec_data.pop("schema", None)
    spec = ResolutionSpecification(**spec_data)
    try:
        saved = resolution_store.save_contract(spec, actor=inp.actor, status="approved")
    except Exception as e:
        raise HTTPException(409, str(e)) from e
    return {"compilation": compiled, "contract": saved}


@app.get("/api/health", tags=["Developer"])
def health():
    return {"ok": True, "service": "arbiter", "version": "0.11.0", "llm": llm.available(), "product": "Resolution Control Infrastructure", "infrastructure": resolution_store.summary()}




@app.get("/api/readiness", tags=["Developer"])
def readiness():
    chain = resolution_store.verify_audit_chain()
    findings = enterprise.configuration_findings()
    ready = chain.get("ok") is True and not any(f["severity"] == "BLOCK" for f in findings)
    payload = {
        "ready": ready,
        "service": "arbiter",
        "version": "0.11.0",
        "audit_chain": chain,
        "configuration_findings": findings,
        "database": resolution_store.summary(),
    }
    if not ready:
        raise HTTPException(status_code=503, detail=payload)
    return payload


@app.get("/api/security-posture", tags=["Developer"])
def security_posture():
    return enterprise.posture()


@app.get("/api/exchange-profiles", tags=["Developer"])
def exchange_profile_registry():
    return {"profiles": exchange_profiles.list_profiles()}

@app.get("/api/markets")
def markets(live: bool = False):
    reports = _reports(live=live)
    pol = policy.load_policy()
    return {"policy_version": pol["version"],
            "source": reports[0]["_source"] if reports else "none",
            "markets": reports}


@app.get("/api/markets/{ticker}")
def market_detail(ticker: str, live: bool = False):
    reports = _CACHE["reports"] or _reports(live=live)
    report = next((r for r in reports if r["ticker"] == ticker), None)
    if not report:
        raise HTTPException(404, "market not found")
    src_val = feeds.get_source_value(report, live=live)
    resolution = engine.resolve(report, src_val)
    packet = evidence.build_packet(report, resolution, src_val)
    return {"report": report, "resolution": resolution, "evidence_packet": packet}


@app.get("/api/monitoring")
def monitor():
    reports = _CACHE["reports"] or _reports()
    return {
        "summary": monitoring.summarize(reports),
        "by_category": monitoring.by_category(reports),
        "lever_pressure": monitoring.lever_pressure(reports),
        "coverage_gaps": monitoring.coverage_gaps(reports),
        "boundary": "read-only intelligence — this view never alters how any contract resolves.",
    }


@app.get("/api/policy")
def get_policy():
    return policy.load_policy()


class PolicyUpdate(BaseModel):
    weights: dict | None = None
    thresholds: dict | None = None
    by: str = "exchange.admin"
    note: str = ""


@app.post("/api/policy")
def post_policy(u: PolicyUpdate, auth=Depends(developer.require_scope("policy:write"))):
    pol = policy.update_policy(u.weights, u.thresholds, u.by, u.note)
    _CACHE["reports"] = None  # rescore next fetch under new policy
    return pol


class AnalyzeIn(BaseModel):
    question: str
    criteria: str
    use_llm: bool = False
    case_id: str | None = None
    source_template_id: str | None = None
    exchange_profile: str = "generic"
    actor: str = "operator:market-ops"


@app.post("/api/analyze")
def analyze(inp: AnalyzeIn, auth=Depends(developer.require_scope("cases:write"))):
    pol = policy.load_policy()
    market = {"ticker": "LIVE-INPUT", "title": inp.question,
              "rules_primary": inp.criteria, "category": "live analysis"}
    report = engine.analyze(market, pol)
    authorities = resolution_store.list_authorities()
    compilation = compiler.compile_rules(
        contract_id="LIVE-INPUT",
        contract_version=1,
        title=inp.question,
        rules=inp.criteria,
        known_authorities=authorities,
        metadata={"source": "live-analysis", "exchange_profile": inp.exchange_profile},
    )
    # Compiler/control gate dominates downstream resolution eligibility.
    if compilation["status"] == "BLOCK":
        resolution = {
            "outcome": "HELD",
            "gate": "COMPILER_BLOCK",
            "trail": [{
                "act": "Resolution HELD",
                "ts": utcnow(),
                "detail": "Contract compilation is BLOCKED. Resolution and payout authorization are disabled until the specification is corrected or governed review changes the state.",
                "sig": canonical_hash({"contract": "LIVE-INPUT", "gate": "COMPILER_BLOCK", "unresolved": compilation.get("unresolved_fields", [])})[:18],
                "hold": True,
            }],
        }
    elif compilation["status"] == "REVIEW":
        resolution = {
            "outcome": "HELD",
            "gate": "COMPILER_REVIEW",
            "trail": [{
                "act": "Human review required",
                "ts": utcnow(),
                "detail": "Contract compilation requires governed human review before automated resolution can proceed.",
                "sig": canonical_hash({"contract": "LIVE-INPUT", "gate": "COMPILER_REVIEW", "unresolved": compilation.get("unresolved_fields", [])})[:18],
                "hold": True,
            }],
        }
    else:
        resolution = engine.resolve(report, None)
    design = intelligence.design_review(report, inp.criteria)
    boundary = exchange_profiles.integration_boundary(inp.exchange_profile, compilation.get("status", ""), resolution.get("outcome", ""))
    out = {"report": report, "resolution": resolution, "design": design, "compilation": compilation, "integration_boundary": boundary}
    saved_case = resolution_store.save_analysis_case(
        title=inp.question, criteria=inp.criteria, result=out, actor=inp.actor,
        case_id=inp.case_id, source_template_id=inp.source_template_id,
    )
    out["case"] = saved_case
    if inp.use_llm:
        try:
            out["llm_triage"] = llm.triage(inp.question, inp.criteria)
        except Exception as e:  # noqa: BLE001
            out["llm_triage"] = {"error": "llm_failed", "message": str(e)}
    return out




@app.get("/api/cases", tags=["Cases"])
def analysis_cases(limit: int = 50):
    return {"cases": resolution_store.list_analysis_cases(limit=min(limit, 200))}


@app.get("/api/cases/{case_id}", tags=["Cases"])
def analysis_case(case_id: str):
    case = resolution_store.get_analysis_case(case_id)
    if not case:
        raise HTTPException(404, "case not found")
    return {"case": case}


class TemplateIn(BaseModel):
    name: str
    title: str
    criteria: str
    source_case_id: str | None = None
    metadata: dict = {}
    actor: str = "operator:market-ops"


class TemplateFromCaseIn(BaseModel):
    name: str
    actor: str = "operator:market-ops"


@app.get("/api/templates", tags=["Cases"])
def contract_templates():
    return {"templates": resolution_store.list_templates()}


@app.post("/api/templates", tags=["Cases"])
def create_template(inp: TemplateIn, auth=Depends(developer.require_scope("cases:write"))):
    try:
        template = resolution_store.save_template(
            name=inp.name, title=inp.title, criteria=inp.criteria, actor=inp.actor,
            source_case_id=inp.source_case_id, metadata=inp.metadata,
        )
    except Exception as e:
        raise HTTPException(409, str(e)) from e
    return {"template": template}


@app.post("/api/cases/{case_id}/template", tags=["Cases"])
def template_from_case(case_id: str, inp: TemplateFromCaseIn, auth=Depends(developer.require_scope("cases:write"))):
    case = resolution_store.get_analysis_case(case_id)
    if not case:
        raise HTTPException(404, "case not found")
    try:
        template = resolution_store.save_template(
            name=inp.name, title=case["title"], criteria=case["criteria"], actor=inp.actor,
            source_case_id=case_id, metadata={"compiler_status": case["compiler_status"]},
        )
    except Exception as e:
        raise HTTPException(409, str(e)) from e
    return {"template": template}


def _portfolio_payload():
    reports = _CACHE["reports"] or _reports()
    ranked = sorted(reports, key=lambda r: (r["composite"], r.get("open_interest", 0)), reverse=True)
    return reports, {
        "summary": monitoring.summarize(reports),
        "lever_pressure": monitoring.lever_pressure(reports),
        "by_category": monitoring.by_category(reports),
        "coverage_gaps": monitoring.coverage_gaps(reports),
        "top_risks": [
            {
                "ticker": r["ticker"],
                "title": r["title"],
                "category": r["category"],
                "composite": r["composite"],
                "verdict": r["verdict"],
                "open_interest": r.get("open_interest", 0),
                "primary_flag": next((f for k in ("definition", "timing", "source") for f in r["levers"][k]["flags"]), None),
            } for r in ranked[:5]
        ],
        "boundary": "portfolio intelligence is read-only and never changes a contract outcome",
    }


@app.get("/api/portfolio")
def portfolio():
    _, payload = _portfolio_payload()
    return payload


@app.get("/api/executive")
def executive_portfolio():
    reports, payload = _portfolio_payload()
    return executive.build(reports, payload, resolution_store.summary())


def _workflow_payload():
    reports, portfolio_payload = _portfolio_payload()
    infra = resolution_store.summary()
    infra["authorities"] = resolution_store.list_authorities()
    evsvc = active_evidence.get_service(resolution_store)
    infra["active_evidence"] = evsvc.summary()
    infra["evidence_exceptions"] = evsvc.list_exceptions(active_only=True)
    exec_payload = executive.build(reports, portfolio_payload, infra)
    queue = workflow.build_work_queue(reports, portfolio_payload, infra, resolution_store.list_work_states())
    brief = workflow.build_agent_brief(queue, exec_payload)
    overview = workflow.build_overview(exec_payload, queue, brief)
    return reports, portfolio_payload, exec_payload, queue, brief, overview


@app.get("/api/overview")
def overview():
    return _workflow_payload()[-1]


@app.get("/api/work-queue")
def work_queue():
    return _workflow_payload()[3]


@app.get("/api/agent/brief")
def agent_brief():
    return _workflow_payload()[4]


class WorkItemUpdate(BaseModel):
    status: str
    owner: str = ""
    note: str = ""
    actor: str = "operator:compliance"


@app.post("/api/work-queue/{work_item_id}")
def update_work_item(work_item_id: str, inp: WorkItemUpdate, auth=Depends(developer.require_scope("operations:write"))):
    # Only state/ownership changes are persisted. The underlying work item is
    # always regenerated from governed Arbiter state.
    queue = _workflow_payload()[3]
    if not any(i["id"] == work_item_id for i in queue.get("items", [])):
        raise HTTPException(404, "work item not found")
    try:
        state = resolution_store.set_work_state(work_item_id, inp.status, inp.owner, inp.note, inp.actor)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    return {"state": state, "queue": _workflow_payload()[3]}


# ---- resolution benchmark ----------------------------------------------------
_BENCHMARK_DATASET = os.path.join(os.path.dirname(__file__), "..", "data", "benchmark", "arb_gold_clean_v0_1.json")
_BENCHMARK_RESULTS = os.path.join(os.path.dirname(__file__), "..", "data", "benchmark", "latest_results.json")

def _load_benchmark_results():
    if not os.path.exists(_BENCHMARK_RESULTS):
        result = run_benchmark(engine, policy.load_policy(), _BENCHMARK_DATASET)
        os.makedirs(os.path.dirname(_BENCHMARK_RESULTS), exist_ok=True)
        import json
        with open(_BENCHMARK_RESULTS, "w") as f:
            json.dump(result, f, indent=2)
        return result
    import json
    with open(_BENCHMARK_RESULTS) as f:
        return json.load(f)

@app.get("/api/benchmark")
def benchmark_summary():
    result = _load_benchmark_results()
    return {
        "benchmark": result.get("benchmark"),
        "metrics": result.get("metrics", {}),
        "methodology": {
            "status": "development/calibration benchmark",
            "external_accuracy_claim": False,
            "note": "Gold Clean v0.1 and its controlled mutations are a development set; use a separate untouched holdout for external claims.",
        },
    }

@app.get("/api/benchmark/cases")
def benchmark_cases(failures_only: bool = False):
    result = _load_benchmark_results()
    cases = result.get("cases", [])
    if failures_only:
        cases = [c for c in cases if (not c.get("validator_pass")) or (c.get("expected_failure_mode") != "NONE" and not c.get("detected")) or (c.get("expected_failure_mode") == "NONE" and c.get("actual_verdict") != "AUTO-RESOLVE")]
    return {"count": len(cases), "cases": cases}

@app.get("/api/benchmark/failures")
def benchmark_failures():
    return benchmark_cases(failures_only=True)

@app.post("/api/benchmark/run")
def benchmark_run(auth=Depends(developer.require_scope("benchmark:run"))):
    import json
    result = run_benchmark(engine, policy.load_policy(), _BENCHMARK_DATASET)
    os.makedirs(os.path.dirname(_BENCHMARK_RESULTS), exist_ok=True)
    with open(_BENCHMARK_RESULTS, "w") as f:
        json.dump(result, f, indent=2)
    return {"benchmark": result.get("benchmark"), "metrics": result.get("metrics", {})}


# ---- v0.6 resolution infrastructure ----------------------------------------
seed_reference_data()

class ContractSpecIn(BaseModel):
    contract_id: str
    contract_version: int = 1
    title: str
    definition: dict
    timing: dict
    authority_ids: list[str]
    source_precedence: list[str] = []
    revision_policy: dict = {}
    fallback_policy: dict = {}
    approval_policy: dict = {}
    metadata: dict = {}
    actor: str = "exchange.market-ops"
    status: str = "draft"

class AuthorityIn(BaseModel):
    authority_id: str
    version: int = 1
    name: str
    organization: str
    source_type: str
    endpoint: str = ""
    dataset: str = ""
    field: str = ""
    precision: str = ""
    revision_behavior: dict = {}
    availability_policy: dict = {}
    approved_contract_classes: list[str] = []
    status: str = "approved"
    metadata: dict = {}
    actor: str = "exchange.compliance"

class EvidenceIn(BaseModel):
    authority_id: str
    authority_version: int = 1
    normalized_value: object
    raw_payload_hash: str
    parser_version: str
    observed_at: str | None = None
    retrieved_at: str | None = None
    contract_id: str | None = None
    effective_at: str | None = None
    revision_number: int = 1
    supersedes: str | None = None
    source_locator: str = ""
    metadata: dict = {}
    actor: str = "system:evidence"

class ResolutionRunIn(BaseModel):
    contract_id: str
    contract_version: int
    policy_version: str
    engine_version: str = "0.6.0"
    evidence_ids: list[str] = []
    state: str = "completed"
    outcome: str
    exceptions: list[dict] = []
    approvals: list[dict] = []
    result: dict = {}
    actor: str = "system:resolver"

@app.get("/api/infrastructure")
def infrastructure_summary():
    return {"version": "0.11.0", "domain": resolution_store.summary(),
            "active_evidence": active_evidence.get_service(resolution_store).summary(),
            "controls": CONTROLS, "principle": "Define → Evidence → Resolve → Audit"}

@app.get("/api/contracts")
def contracts_registry():
    return {"contracts": resolution_store.list_contracts()}

@app.post("/api/contracts")
def create_contract(inp: ContractSpecIn, auth=Depends(developer.require_scope("contracts:write"))):
    spec = ResolutionSpecification(**inp.model_dump(exclude={"actor", "status"}))
    known = {a["authority_id"] for a in resolution_store.list_authorities()}
    controls = evaluate_spec(spec.to_dict(), known)
    if any(c["status"] == "BLOCK" for c in controls):
        raise HTTPException(422, {"error": "contract_control_failure", "controls": controls})
    try:
        saved = resolution_store.save_contract(spec, actor=inp.actor, status=inp.status)
    except Exception as e:
        raise HTTPException(409, str(e)) from e
    return {"contract": saved, "controls": controls}

@app.get("/api/contracts/{contract_id}/resolution-spec")
def get_resolution_spec(contract_id: str):
    spec = resolution_store.latest_contract(contract_id)
    if not spec:
        raise HTTPException(404, "contract not found")
    known = {a["authority_id"] for a in resolution_store.list_authorities()}
    return {"spec": spec, "controls": evaluate_spec(spec, known)}

@app.get("/api/authorities")
def authorities_registry():
    return {"authorities": resolution_store.list_authorities()}

@app.post("/api/authorities")
def create_authority(inp: AuthorityIn, auth=Depends(developer.require_scope("authorities:write"))):
    authority = Authority(**inp.model_dump(exclude={"actor"}))
    try:
        saved = resolution_store.save_authority(authority, actor=inp.actor)
    except Exception as e:
        raise HTTPException(409, str(e)) from e
    return {"authority": saved}

@app.get("/api/evidence")
def evidence_registry(contract_id: str | None = None, limit: int = 100):
    return {"evidence": resolution_store.list_evidence(contract_id=contract_id, limit=min(limit, 500))}

@app.post("/api/evidence")
def append_evidence(inp: EvidenceIn, auth=Depends(developer.require_scope("evidence:write"))):
    record = EvidenceRecord(
        evidence_id=gen_id("evid"), authority_id=inp.authority_id, authority_version=inp.authority_version,
        observed_at=inp.observed_at or utcnow(), retrieved_at=inp.retrieved_at or utcnow(),
        normalized_value=inp.normalized_value, raw_payload_hash=inp.raw_payload_hash, parser_version=inp.parser_version,
        contract_id=inp.contract_id, effective_at=inp.effective_at, revision_number=inp.revision_number,
        supersedes=inp.supersedes, source_locator=inp.source_locator, metadata=inp.metadata)
    try:
        saved = resolution_store.append_evidence(record, actor=inp.actor)
    except Exception as e:
        raise HTTPException(422, str(e)) from e
    return {"evidence": saved, "controls": evaluate_evidence(saved)}

@app.get("/api/resolution-runs")
def resolution_runs(contract_id: str | None = None, limit: int = 100):
    return {"runs": resolution_store.list_runs(contract_id=contract_id, limit=min(limit, 500))}

@app.post("/api/resolution-runs")
def create_resolution_run(inp: ResolutionRunIn, auth=Depends(developer.require_scope("resolution:write"))):
    controls = evaluate_run(inp.model_dump())
    if any(c["status"] == "BLOCK" for c in controls):
        raise HTTPException(422, {"error": "resolution_control_failure", "controls": controls})
    run = ResolutionRun(
        run_id=gen_id("run"), contract_id=inp.contract_id, contract_version=inp.contract_version,
        policy_version=inp.policy_version, engine_version=inp.engine_version, evidence_ids=inp.evidence_ids,
        control_results=controls, state=inp.state, outcome=inp.outcome, started_at=utcnow(), completed_at=utcnow(),
        exceptions=inp.exceptions, approvals=inp.approvals, result=inp.result)
    try:
        saved = resolution_store.save_run(run, actor=inp.actor)
    except Exception as e:
        raise HTTPException(422, str(e)) from e
    return {"run": saved, "controls": controls}

@app.get("/api/audit")
def audit_log(limit: int = 100, object_type: str | None = None, object_id: str | None = None):
    return {"chain": resolution_store.verify_audit_chain(),
            "events": resolution_store.audit_log(limit=min(limit, 500), object_type=object_type, object_id=object_id)}


# ---- v0.11 Active Evidence Infrastructure ----
class EvidenceMonitorIn(BaseModel):
    contract_id: str
    authority_id: str
    authority_version: int = 1
    adapter_type: str = "static"
    config: dict = {}
    schedule_seconds: int = 300
    enabled: bool = True
    actor: str = "system:evidence-ops"

class EvidenceMonitorUpdate(BaseModel):
    config: dict | None = None
    schedule_seconds: int | None = None
    enabled: bool | None = None
    actor: str = "system:evidence-ops"

class EvidenceObservationIn(BaseModel):
    normalized_value: object
    raw_payload: object
    observed_at: str | None = None
    source_locator: str = ""
    parser_version: str = "active-evidence.v1"
    actor: str = "system:evidence-worker"

@app.get("/api/evidence-monitors", tags=["Active Evidence"])
def list_evidence_monitors(contract_id: str | None = None):
    return {"monitors": active_evidence.get_service(resolution_store).list_monitors(contract_id)}

@app.post("/api/evidence-monitors", tags=["Active Evidence"])
def create_evidence_monitor(inp: EvidenceMonitorIn, auth=Depends(developer.require_scope("evidence:write"))):
    try:
        monitor = active_evidence.get_service(resolution_store).create_monitor(**inp.model_dump())
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    return {"monitor": monitor}

@app.post("/api/evidence-monitors/{monitor_id}", tags=["Active Evidence"])
def update_evidence_monitor(monitor_id: str, inp: EvidenceMonitorUpdate, auth=Depends(developer.require_scope("evidence:write"))):
    try:
        monitor = active_evidence.get_service(resolution_store).update_monitor(monitor_id, **inp.model_dump())
    except ValueError as e:
        raise HTTPException(404 if "not found" in str(e) else 422, str(e)) from e
    return {"monitor": monitor}

@app.post("/api/evidence-monitors/{monitor_id}/observe", tags=["Active Evidence"])
def observe_evidence(monitor_id: str, inp: EvidenceObservationIn, auth=Depends(developer.require_scope("evidence:write"))):
    try:
        result = active_evidence.get_service(resolution_store).observe(monitor_id, **inp.model_dump())
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    return result.to_dict()

@app.post("/api/evidence-monitors/{monitor_id}/poll", tags=["Active Evidence"])
def poll_evidence_monitor(monitor_id: str, auth=Depends(developer.require_scope("evidence:write"))):
    try:
        return active_evidence.get_service(resolution_store).poll(monitor_id)
    except ValueError as e:
        raise HTTPException(404 if "not found" in str(e) else 422, str(e)) from e

@app.post("/api/evidence-poll-due", tags=["Active Evidence"])
def poll_due_evidence(limit: int = 50, auth=Depends(developer.require_scope("evidence:write"))):
    return active_evidence.get_service(resolution_store).poll_due(limit=min(limit, 100))

@app.get("/api/source-health", tags=["Active Evidence"])
def source_health():
    return active_evidence.get_service(resolution_store).source_health()

@app.get("/api/evidence-exceptions", tags=["Active Evidence"])
def evidence_exceptions(active_only: bool = True):
    return {"exceptions": active_evidence.get_service(resolution_store).list_exceptions(active_only=active_only)}

@app.get("/api/resolution-reevaluations", tags=["Active Evidence"])
def resolution_reevaluations(status: str | None = None):
    return {"requests": active_evidence.get_service(resolution_store).list_reevaluations(status=status)}


# ---- static frontend ----
if os.path.isdir(_FRONTEND):
    @app.get("/")
    def index():
        return FileResponse(os.path.join(_FRONTEND, "index.html"))

    app.mount("/", StaticFiles(directory=_FRONTEND), name="static")
