# Arbiter — Resolution Intelligence Platform (v0.4)

Arbiter is an auditable resolution-intelligence platform for event contracts. It helps market operators **design**, **monitor**, **resolve**, **explain**, and **audit** event contracts without turning an opaque model into the authority that decides payouts.

## v0.4 product loop

**Define → Monitor → Resolve → Explain → Audit**

### 1. Contract Intelligence
Paste draft resolution terms before listing. Arbiter runs the governed Source / Timing / Definition engine, identifies structural deficiencies, calculates listing readiness, and generates deterministic drafting recommendations.

### 2. Resolution Workspace
Every contract keeps its original rules, lever scores, verdict, authoritative source observation, deterministic evaluation, and resolution trail together in one case view.

### 3. Evidence Packets
Each market detail response now includes a portable `arbiter.evidence.v1` packet with three visibly separate authorities:
- contract authority — the published resolution terms
- resolution authority — the designated evidence source
- governance authority — the versioned Arbiter policy

The packet is canonicalized and SHA-256 hashed.

### 4. Portfolio Intelligence
The read-only intelligence layer now reports summary risk, category concentration, lever pressure, held notional, coverage gaps, and the highest-risk contracts. It can recommend what humans should improve, but it never changes a contract outcome.

## Core boundary

The deterministic rule engine remains the system of record. Optional LLM triage may detect, classify, summarize, or explain ambiguity, but it never overrides governed adjudication logic.

## Run locally

```bash
./start.sh
```

Then open `http://localhost:8000`.

The launcher installs backend/frontend dependencies, builds the React/Vite frontend into `backend/dist`, and starts FastAPI on port 8000.

## API

- `GET /api/health`
- `GET /api/markets`
- `GET /api/markets/{ticker}` — scored report + resolution trail + evidence packet
- `GET /api/monitoring`
- `GET /api/portfolio` — portfolio resolution intelligence
- `GET /api/policy`
- `POST /api/policy`
- `POST /api/analyze` — contract intelligence review + drafting fixes

## New backend modules

- `backend/app/intelligence.py` — pre-listing design review and drafting recommendations
- `backend/app/evidence.py` — portable hashed evidence packet

## Existing core preserved

- `engine.py` — deterministic Source / Timing / Definition scoring and resolution
- `policy.py` — versioned weights/thresholds
- `feeds.py` — market and authoritative-source adapters
- `monitoring.py` — read-only portfolio intelligence
- `llm.py` — optional non-binding triage
