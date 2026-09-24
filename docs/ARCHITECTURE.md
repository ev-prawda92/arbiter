# Architecture

Arbiter is one FastAPI service with a React front end, backed by a single resolution store.
Engines are plain Python modules with no framework coupling, and each one is covered by its own gate script.

## Request path

`backend/app/server.py` is the entry point (`uvicorn app.server:app`). It takes the API from
`main.py`, adds the decision router from `decision_api.py`, and mounts the built front end
(`backend/dist`) **last**, so that static files never shadow an API route. The decision API
route gate checks that ordering.

`backend/app/public.py` is a separate, narrower app for the public Resolution API (`/v1/...`),
with its own rate limits (`public_limits.py`) and its own gate.

## The resolution loop

| Stage | Module | What it does |
|---|---|---|
| Intake | `venue_intake.py` | Normalizes Kalshi and Polymarket markets, open and settled. Classifies each for hardness and routes flagged ones to a work-item kind. Re-triages when the classifier changes. |
| Interpret | `compiler.py`, `semantic_contract.py`, `intelligence.py` | Turns resolution text into a structured specification (operator, threshold, source, timing) with character-span provenance. Flags subjective terms. |
| Score | `engine.py`, `policy.py` | Deterministic Source / Timing / Definition scoring against versioned policy weights. |
| Evidence | `resolution_infra.py`, `active_evidence.py`, `evidence.py` | Append-only evidence with provenance hashes; hashed evidence packets. |
| Queue | `operations_intelligence.py`, `workflow.py` | Groups cases by shared root cause (blocker + normalized action) so one decision can answer many cases. |
| Decide | `decision_records.py`, `decision_operations.py`, `decision_api.py` | Governed, versioned decision records. An authoritative decision clears the cases it answers. Some blockers are never auto-cleared. |
| Approve | `approval_control.py`, `governed_policy.py` | Approval workflow and signed settlement packets. Production refuses to sign without a real key. |
| Audit | `resolution_infra.py` | Every state change is written to `audit_events`, a hash chain that can be verified end to end. |

## Storage

`ResolutionStore` (`resolution_infra.py`) uses SQLite locally, with WAL enabled.
`production_data.py` adds a PostgreSQL adapter with request-scoped tenants, row-level security
and content-addressed evidence storage. Production configuration fails closed unless PostgreSQL
and object storage are configured.

Runtime state (the database, `backend/data/policy.json`) is not committed. Point it elsewhere
with `ARBITER_DATABASE_PATH` and `ARBITER_POLICY_PATH`.

## Supporting subsystems

| Module | Role |
|---|---|
| `model_gateway.py`, `llm.py` | Optional LLM access through a governed gateway. Advisory only: it never decides an outcome. Off by default. |
| `identity_tenant.py`, `identity_federation.py`, `developer.py` | Tenants, API keys with scopes, and an OIDC foundation. |
| `enterprise.py`, `enterprise_secrets.py` | Runtime config findings. Readiness is blocked on unsafe production config. |
| `reliability.py`, `operations_resilience.py`, `resilience_lab.py` | Backpressure, incident lifecycle, recovery drills. |
| `settlement_assurance.py`, `external_assurance.py` | Adversarial contract validation and the certification blocker checklist. |
| `reference_exchange.py` | Play-money exchange for end-to-end testing of market → trade → resolve → payout. |
| `shadow_pilot.py` | Harness for running Arbiter in shadow alongside a partner's live process. |
| `real_benchmark/` | Blind, hash-pinned benchmark on resolved contracts. Also contains the hardness classifier (`hardness.py`) that venue intake uses. |
| `engine_v0_4_frozen.py` | Frozen copy of an earlier engine, kept so that published benchmark results stay reproducible. Not used for live scoring. |

## Front end

The front end is built with Vite and has three entry pages that compile to `backend/dist`:

- `index.html` → `main.jsx`: home, exposure view, exception workspace, contract design review.
- `console.html` → `ConsoleShell.jsx`: operations console and case workspace.
- `decision-workbench.html` → `DecisionWorkbench.jsx`: decision recording and clearing outcome.

## Tests

- `tests/`: pytest unit tests, repository invariants, and recorded venue scans for offline replay.
- `scripts/*_gate.py`: 26 gate scripts. Each one drives a subsystem through its API and asserts on
  outcomes, hashes and audit state.
- `scripts/release_gate.py`: 452 checks across 18 suites.
- `make check`: runs all of the above. See the [README](../README.md).
