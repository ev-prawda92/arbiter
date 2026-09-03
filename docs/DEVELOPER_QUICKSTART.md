# Arbiter Developer Quickstart — v0.9 Preview

Arbiter exposes a REST API for contract design, governed authorities, evidence, resolution runs, workflow, portfolio intelligence, and audit.

## Run locally

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

Interactive reference:

- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`
- OpenAPI: `http://127.0.0.1:8000/openapi.json`

## Authentication

Local development remains open by default. To require API keys:

```bash
export ARBITER_API_KEYS="arb_dev_example,arb_second_key"
```

Then send:

```http
X-Arbiter-Key: arb_dev_example
```

## 1. Compile natural-language rules

```bash
curl -s http://127.0.0.1:8000/api/compile \
  -H 'Content-Type: application/json' \
  -d '{
    "contract_id":"DEMO-CPI-001",
    "title":"Will CPI be above 3.0% on Sep 11, 2026?",
    "rules":"Resolves YES if the BLS CPI year-over-year value is above 3.0% on Sep 11, 2026 at 08:30 EDT. First release controls."
  }'
```

The compiler returns a proposed `ResolutionSpecification`, field-level provenance, unresolved fields, controls, a READY/REVIEW/BLOCK status, and a compilation hash.

## 2. Persist a governed contract

Use `POST /api/contracts` only after the proposed specification is complete and controls permit creation.

## 3. Append evidence

`POST /api/evidence` creates an append-only evidence record tied to an authority/version with retrieval time, raw payload hash, parser version, and record hash.

## 4. Create a resolution run

`POST /api/resolution-runs` pins contract version, policy version, engine version, evidence IDs, controls, exceptions, approvals, and outcome.

## 5. Inspect workflow and audit

- `GET /api/work-queue`
- `GET /api/overview`
- `GET /api/portfolio`
- `GET /api/audit`

The audit endpoint verifies the hash chain and returns recent control-plane events.

## Safety boundary

The compiler and advisory agent can parse, detect ambiguity, triage, explain, and recommend. They do not silently modify binding outcomes. Settlement remains governed by deterministic resolution controls.
