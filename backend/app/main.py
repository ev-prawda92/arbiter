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
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import engine, feeds, monitoring, policy, llm

app = FastAPI(title="Arbiter", version="0.3.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_FRONTEND = os.path.join(os.path.dirname(__file__), "..", "..", "frontend")

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


@app.get("/api/health")
def health():
    return {"ok": True, "service": "arbiter", "version": "0.3.0", "llm": llm.available()}


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
    return {"report": report, "resolution": resolution}


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
def post_policy(u: PolicyUpdate):
    pol = policy.update_policy(u.weights, u.thresholds, u.by, u.note)
    _CACHE["reports"] = None  # rescore next fetch under new policy
    return pol


class AnalyzeIn(BaseModel):
    question: str
    criteria: str
    use_llm: bool = False


@app.post("/api/analyze")
def analyze(inp: AnalyzeIn):
    pol = policy.load_policy()
    market = {"ticker": "LIVE-INPUT", "title": inp.question,
              "rules_primary": inp.criteria, "category": "live analysis"}
    report = engine.analyze(market, pol)
    resolution = engine.resolve(report, None)
    out = {"report": report, "resolution": resolution}
    if inp.use_llm:
        try:
            out["llm_triage"] = llm.triage(inp.question, inp.criteria)
        except Exception as e:  # noqa: BLE001
            out["llm_triage"] = {"error": "llm_failed", "message": str(e)}
    return out


# ---- static frontend ----
if os.path.isdir(_FRONTEND):
    @app.get("/")
    def index():
        return FileResponse(os.path.join(_FRONTEND, "index.html"))

    app.mount("/", StaticFiles(directory=_FRONTEND), name="static")
