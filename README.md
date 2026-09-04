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

## v0.6 — Resolution Control Infrastructure

Arbiter now includes a persistent reference control plane for the settlement lifecycle:

**Define → Evidence → Resolve → Audit**

Core domain objects:
- `ResolutionSpecification` — version-pinned executable contract semantics.
- `Authority` — governed resolution source definitions and versions.
- `EvidenceRecord` — append-only normalized observations with provenance hashes.
- `ResolutionRun` — replayable, version-pinned resolution executions.

The v0.6 control library adds technical governance checks (`RES-001`–`RES-008`),
including authority requirements, settlement timing, source precedence, evidence provenance,
version pinning, and exception disposition. A SHA-256 hash-chained audit log records all
control-plane mutations.

New APIs include `/api/infrastructure`, `/api/contracts`, `/api/authorities`, `/api/evidence`,
`/api/resolution-runs`, and `/api/audit`.

These controls support operational governance and auditability; they are not a legal
determination of regulatory compliance.

## v0.7 — Executive Portfolio Intelligence

Arbiter now exposes the resolution-control state as a shared executive operating layer. Compliance, Market Operations, Finance, and leadership use the same underlying contract/evidence/resolution data through role-specific read-only lenses. The Portfolio view surfaces resolution-risk notional, held pre-payout exposure, dominant ambiguity drivers, category concentration, highest-risk contracts, coverage gaps, and audit-chain status.

New API: `GET /api/executive`.

## v0.8 — Operational Workflow

Arbiter now presents two distinct operating surfaces on top of the same governed resolution state:

**Executive Overview** — a read-only, low-click view of portfolio posture, payout holds, resolution-risk notional, primary risk drivers, audit integrity, and the most important actions.

**Compliance / Resolution Operations Work Queue** — a prioritized exception queue for the people doing the work. HOLDs, monitored contracts, authority issues, evidence gaps, and audit-integrity failures become actionable work items with persisted operator status.

The first **Arbiter Resolution Operations Agent** sits above the control plane as an advisory layer. It summarizes and prioritizes; it cannot change contract terms, evidence, policy, settlement outcomes, or payout authorization.

New APIs: `/api/overview`, `/api/work-queue`, `/api/work-queue/{work_item_id}`, and `/api/agent/brief`.

## v0.9 — Developer Platform + Resolution Compiler

Arbiter can now be consumed as infrastructure, not only through its operator UI.

Developer surfaces:

- `/docs` — interactive Swagger API documentation
- `/redoc` — ReDoc API reference
- `/openapi.json` — machine-readable OpenAPI schema
- `/api/developer` — developer-platform manifest
- `docs/DEVELOPER_QUICKSTART.md` — integration walkthrough
- `sdk/python/arbiter_sdk.py` — dependency-free Python SDK preview

The new Resolution Compiler connects prose market rules to the governed v0.6 domain model:

**Natural-language rules → proposed ResolutionSpecification → controls → READY / REVIEW / BLOCK**

`POST /api/compile` returns the proposed specification, source spans/provenance, unresolved fields, technical controls, compiler version, and compilation hash. It does not fabricate missing fields. `POST /api/compile-and-create` only persists a contract when compilation is READY.

API-key protection can be enabled for writes by setting `ARBITER_API_KEYS` and sending `X-Arbiter-Key`. Local development remains open when the environment variable is unset.

## v0.9.2 — Resolution Gate Coherence

The compiler is now an authoritative pre-resolution gate. `BLOCK` and `REVIEW` states hold automated resolution; only `READY` contracts may continue to normal evidence-bound resolution. Live analysis returns compilation, integrity analysis, and gated resolution atomically to prevent inconsistent UI states. Title/rules conflicts are compiled from governing rules only, and title-derived fields are marked conflicted rather than trusted.

## v0.9.3 — Review Semantics

Arbiter now distinguishes repairable specification incompleteness from hard blocking defects. A coherent contract with an approved authority, objective condition, and recognizable settlement window can enter `REVIEW` when details such as exact cutoff time or timezone remain missing. `BLOCK` is reserved for hard inconsistencies or missing binding concepts. Compiler results also include deterministic recommended drafting fixes.

## v0.9.4 — Case Registry & Templates

Arbiter now retains every contract review as a saved **Analysis Case**. Reopening and rerunning a case appends a run to its history rather than requiring the operator to re-enter the market question and resolution criteria. Reusable **Contract Templates** can be created from prior cases and used to prefill new cases, while every derived contract is recompiled and re-evaluated under current controls.

New workflow: **Template or New Draft → Saved Case → Compile/Review → Revise/Rerun → Approve → Monitor → Resolve**.

## v0.9.5 — Automated coherence harness

Run the full API-driven release smoke test against a running local Arbiter instance:

```bash
python3 scripts/coherence_test.py
```

Canonical fixtures live at `tests/fixtures/coherence_cases.json`. The harness validates READY / REVIEW / BLOCK semantics, saved-case reruns, templates, cross-surface APIs, developer docs, audit-chain integrity, and the current development benchmark baseline. See `COHERENCE_TEST_PLAN.md`.

## v0.10 enterprise boundary
For production-oriented deployments, Arbiter now supports production-default auth, hashed/scoped API keys, explicit CORS origins, request/security headers, readiness gates, and venue-specific settlement boundaries. See `ENTERPRISE_READINESS.md` and `EXCHANGE_FIT.md`.

## v0.11 — Active Evidence Infrastructure
Arbiter can now register governed evidence monitors, capture normalized observations, preserve append-only revisions, detect source conflicts/outages, create reevaluation requests, and surface evidence exceptions into the Work Queue.

Run the worker locally:
```bash
python3 scripts/evidence_worker.py --base-url http://127.0.0.1:8000
```
For a single due-poll cycle:
```bash
python3 scripts/evidence_worker.py --once
```
HTTP source adapters are disabled by default. They require approved HTTPS authority endpoints and `ARBITER_ENABLE_HTTP_SOURCE_ADAPTERS=true`.

Release gates:
```bash
python3 scripts/coherence_test.py
python3 scripts/enterprise_gate.py
python3 scripts/evidence_gate.py
```
