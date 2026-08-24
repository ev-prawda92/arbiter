# Arbiter — Independent Resolution Layer for Event Contracts

A SaaS platform that audits event-contract resolution terms and produces independent verdicts before money moves. Built for Kalshi and other CFTC-regulated prediction markets.

## The Pitch

When Kalshi faces a settlement dispute, regulators ask: *"You write the rules, you determine the settlement, you judge the outcome — where is the independence?"*

Arbiter answers: A third-party adjudication engine that scores every contract's resolution criteria on three transparent levers (source, timing, definition), produces a signed verdict, and — critically — *holds contracts that can't resolve cleanly for human review before any payout*. The logic is auditable by design. The policy is governed and versioned. Every decision is written to an immutable ledger with a hash.

That's not just compliance theater — it's structural de-risking.

## Running Locally

### Prerequisites
- Python 3.10+ (backend)
- Node 18+ (frontend build)

### Quick start
```bash
cd arbiter
./start.sh
```

Then open http://localhost:8000.

The script will:
1. Install Python dependencies (FastAPI, uvicorn, httpx)
2. Install Node dependencies
3. Build the React frontend
4. Start the FastAPI server on port 8000

### Manual startup (if you prefer)

**Backend:**
```bash
cd backend
pip install --break-system-packages fastapi uvicorn httpx
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

**Frontend (in another terminal):**
```bash
cd frontend
npm install
npm run dev  # runs on http://localhost:5173 with proxy to /api)
```

## Architecture

```
frontend/           React app, served as static by the backend
├── src/
│   ├── main.jsx    Entry point, all components in one file
│   └── styles.css  Institutional design system
├── vite.config.js  Config (proxies /api to backend)
└── package.json

backend/            FastAPI server
├── app/
│   ├── main.py     FastAPI app, routes, static serving
│   ├── engine.py   Core scoring engine (deterministic, rule-based)
│   ├── policy.py   Governed policy (weights, thresholds, changelog)
│   ├── feeds.py    Data feeds (Kalshi markets, NWS weather data)
│   ├── monitoring.py  Read-only platform intelligence
│   └── llm.py      Optional LLM triage (Anthropic API)
├── data/
│   ├── sample_markets.json    Sample markets to score
│   └── sample_sources.json    Sample resolution values (demo data)
└── dist/           Built frontend (static)

API Endpoints:
  GET  /api/health              Health check
  GET  /api/markets             All scored markets
  GET  /api/markets/{ticker}    Single market + resolution trail
  GET  /api/monitoring          Platform-level intelligence
  GET  /api/policy              Current policy + changelog
  POST /api/policy              Governed policy update (logged)
  POST /api/analyze             Score arbitrary pasted contract
```

## Key Design Decisions

### 1. Rule-Based Scoring (No Black Box)
The entire value of an *independent* resolution layer is that the logic doesn't live inside the exchange's own walls. So the scoring engine is 100% deterministic, inspectable heuristics. No opaque models. Every score is produced by explicit rules, every flag has a reason, and you can audit line-by-line why a contract got the verdict it got.

### 2. Three Levers
Every contract is scored on three factors that decide who gets paid:
- **Source**: Is there one authoritative, timely settlement source with a fallback?
- **Timing**: Is the settlement clock exact (date + time + timezone, with revision handling)?
- **Definition**: Does the question map to a cleanly verifiable fact (no subjective terms)?

Each lever is 0-100 where HIGHER = MORE dispute risk.

### 3. Governed Configurability
The weights (30/30/40 by default) and thresholds (clean ≤20, monitored ≤50, review >50) are set by Kalshi's team, but every change is versioned, timestamped, and logged. No quiet policy shifts. That's what makes the independence claim actually true.

### 4. Read-Only Monitoring
The platform intelligence layer (by_category, lever_pressure, coverage_gaps) observes and reports. It never feeds back into how individual contracts resolve. The per-contract engine stays deterministic and evidence-bound. What Kalshi does with the monitoring signals is their call.

### 5. Resolution Trails
Every resolved market gets a timestamped ledger of what happened: criteria parsed, source polled, condition evaluated, outcome written. Each step has a hash. That's auditable proof that the right contract got the right outcome.

## Sample Data

The app ships with 10 representative Kalshi-shaped markets:
- Weather (NYC temp, Miami rain)
- Commodities (WTI oil, copper)
- Macro (FOMC rate cut, CPI, recession)
- Geopolitics (ceasefire)
- Crypto (Bitcoin at $100k)

Current scoring: 2 clean, 7 monitored, 1 held for review. The ceasefire market legitimately holds — interpretive terms, no authority source, no snapshot rule.

## For a Real Kalshi Pitch

**Do this next:**
1. Rebuild the docket from real Kalshi markets (scrape /markets or connect via API with auth)
2. Include the Jan 2026 shutdown market that settled ~13 hours apart across venues (the centerpiece example)
3. Run the analyzer live over those actual terms
4. Build the economic argument: disputes-prevented × notional-at-risk × reputational cost

**Then:**
1. Wire the live analyzer to ingest a Kalshi contract URL and score it on-the-fly
2. Add a "drafting fix" output that rewrites flagged terms to close ambiguity
3. Build a policy-update UI so Kalshi can govern their own thresholds inside the app

## Environment Variables

```bash
KALSHI_BASE="https://api.elections.kalshi.com/trade-api/v2"  # Kalshi API endpoint
KALSHI_API_KEY=""                                             # Kalshi API key (optional)
FEED_TIMEOUT="6"                                              # Timeout for live feeds (seconds)
ANTHROPIC_API_KEY=""                                          # For optional LLM triage
ANTHROPIC_MODEL="claude-sonnet-4-6"                          # LLM model to use
```

All feeds have graceful fallback to sample data if endpoints are unreachable or unauthenticated.

## File Structure

```
arbiter/
├── README.md                    <- you are here
├── start.sh                     <- one-command startup
├── backend/
│   ├── app/                    (see above)
│   ├── data/
│   ├── dist/                   (built frontend, auto-generated)
│   └── requirements.txt         (optional, for pip install -r)
├── frontend/
│   ├── src/
│   ├── package.json
│   ├── vite.config.js
│   ├── index.html
│   └── node_modules/           (auto-generated)
```

## Design Language

The UI follows an institutional, audit-trail aesthetic. Dark ink rail, cool paper background, monospace for technical detail. Everything is purposefully minimal — no animations beyond what helps clarity, no bright colors except for verdict signals (seal green for clean, ochre for monitored, brick red for review). The intent is: *this is serious infrastructure, not a toy.*

## To Extend

**Add a new feed source:**
Edit `backend/app/feeds.py`. Each feed has a live adapter (with timeout + sample fallback) and a normalized return shape.

**Adjust scoring logic:**
Edit `backend/app/engine.py`. The three `score_*` functions are independent and inspectable. Change weights in `backend/app/policy.py`.

**Change the UI:**
Edit `frontend/src/main.jsx` and `frontend/src/styles.css`. React state is local to the App component; API calls are async fetches.

**Add an endpoint:**
Edit `backend/app/main.py`. FastAPI auto-generates OpenAPI docs at `/docs` (disabled in this build, but easy to enable).

## Notes

- The frontend builds to `backend/dist` and is served as static files by the FastAPI app.
- All data is in-memory; there's no database. For production, add a backing store (PostgreSQL, DynamoDB, etc.) and persist the policy changelog.
- The optional LLM triage (llm.py) requires an Anthropic API key. If absent, the triage endpoint explains why and the app still works fine.
- Weather markets can genuinely auto-resolve using live NWS data (US-only). Other markets resolve against sample data in the demo.

## Questions?

This is a living prototype. The scoring thresholds, lever weights, and all policy can be tuned. The architecture is designed for extensibility: plug in live Kalshi markets, add new adjudication criteria, wire in a database, deploy to production.

What matters is the thesis: *independent, auditable, verifiable*. Everything else is tuning.
