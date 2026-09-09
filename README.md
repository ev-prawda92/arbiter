# Arbiter

## v0.27 — Real-World Resolution Benchmark

Arbiter v0.27 freezes the product surface at a pilot-ready baseline and moves validation toward untouched real-world contracts. The release adds `ARB-GOLD-HOLDOUT-v0.1`: a label-separated, hash-pinned benchmark protocol for 50–100 already-resolved event contracts.

The benchmark pipeline is:

**Collect candidates → Curate → Freeze → Verify → Run blind → Pin predictions → Score → Report**

Key controls:
- contract inputs and independent evidence are physically separated from outcome/gold labels;
- the blind runner reads only contracts + frozen evidence and never opens the label file;
- contracts, evidence, labels, provenance, predictions, and reports are SHA-256 pinned;
- READY contracts can resolve deterministically from supported evidence; non-READY/missing-evidence cases HOLD rather than guess;
- frozen datasets cannot be overwritten;
- missing evidence/gold coverage remains explicitly unscored;
- the holdout must never be used to tune Arbiter.

Current release validation target: **452/452 checks across 18 suites**. This is internal engineering validation, not independent accuracy, regulatory approval, or production settlement certification.

See `REAL_WORLD_BENCHMARK.md`, `CHANGELOG_V0_27.md`, and `VALIDATION_V0_27.md`.

## v0.21 — Reference Exchange, Production Operations & Settlement Assurance

Arbiter has advanced through three additional integration-hardening milestones:

- **v0.19 Reference Exchange** — a play-money end-to-end harness proving contract semantics, market opening gates, positions, sandbox resolution, payout ledger, settlement hash, and audit trail.
- **v0.20 Production Operations & Resilience** — dependency health, backpressure, incident lifecycle, bounded-load admission, and deterministic recovery drills.
- **v0.21 Settlement Assurance** — adversarial contract validation, frozen holdout registries, hash-pinned assurance reports, and an explicit certification blocker checklist.

Current local release validation: **334/334 checks across 13 suites**. This remains internal release evidence, **not independent production settlement certification**. v0.21 explicitly reports `production_settlement_certified: false` until external security review, penetration testing, a real untouched holdout, and deployment-backed resilience evidence are complete.

## v0.17 — Production Data Plane

**Semantic Contract Intelligence + Resolution Control for Event Markets**

Arbiter v0.17 moves the core platform from a SQLite-only reference store toward a production-shaped data plane. The release adds a PostgreSQL adapter, request-scoped tenant context, database-enforced row-level security, content-addressed raw evidence storage, concurrency serialization for settlement packet creation, and backup/restore verification hooks. Local development remains SQLite-based; production configuration fails closed unless PostgreSQL and managed object storage are configured.

The binding principle remains:

> **AI interprets. Policy governs. Evidence proves. Deterministic logic resolves. Humans handle exceptions.**

Release validation: **240/240 checks across 9 suites** in the local reference environment. This is a release-coherence result, **not production settlement certification**.

The remaining work is deployment and assurance: actual managed PostgreSQL/object storage, SSO and key custody, managed workers/queues, HA/failover, external observability, backup/PITR drills, load/chaos testing, independent security review, penetration testing, and untouched real-contract holdout validation.

See `PRODUCTION_DATA_PLANE.md`, `CHANGELOG_V0_17.md`, `VALIDATION_V0_17.md`, and `ENTERPRISE_READINESS.md`.

Arbiter interprets what natural-language event contracts mean, converts that meaning into governed resolution specifications, monitors authoritative evidence, executes deterministic resolution logic, controls approvals and settlement handoffs, and preserves an auditable record.

> AI interprets. Policy governs. Evidence proves. Deterministic logic resolves. Humans handle exceptions.

## v0.13

Semantic Contract Intelligence is now a first-class subsystem. See `SEMANTIC_CONTRACT_INTELLIGENCE.md`, `CHANGELOG_V0_13.md`, and `VALIDATION_V0_13.md`.

## Current product loop

**Define → Evidence → Resolve → Approve → Authorize → Audit**

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


## v0.12 — Approval & Settlement Control

Arbiter now adds a governed authorization boundary between a deterministic resolution outcome and any downstream settlement/oracle workflow. The release introduces maker-checker approval requests, duplicate-decision prevention, signed settlement authorization packets, venue-specific terminal handoff semantics, and a governed policy draft workflow.

The settlement boundary is deliberately explicit: **v0.12 creates authorization packets; it does not execute an exchange settlement or an oracle transaction.** Kalshi/DCM-profile runs produce an exchange-resolution authorization handoff. Polymarket/UMA-profile runs produce an oracle proposal/dispute handoff packet.

Policy changes can now follow **Draft → Submit → Independent Approval → Activate**. In production mode direct active-policy mutation is blocked. Existing resolution runs remain pinned to the policy version they used.

Validation gate: `python3 scripts/settlement_gate.py`.

## v0.18 — Enterprise Secrets, Model Administration & Identity Federation

Arbiter now supports tenant-governed model providers, write-only credential administration, local encrypted secret custody, an AWS Secrets Manager/KMS production adapter, and OIDC bearer-token federation. Frontier models remain advisory only and cannot determine or authorize settlement.

## v0.22–v0.26 Enterprise Validation Program

Arbiter now includes an explicit path from enterprise architecture to enterprise proof:

- **v0.22 Cloud Deployment Foundation** — production Docker image and AWS reference Terraform for ECS Fargate, Multi-AZ RDS PostgreSQL, S3/KMS, Secrets Manager, HTTPS ALB, CloudWatch and autoscaling.
- **v0.23 Resilience Validation Lab** — deterministic local stress scenarios plus a registry for deployed load, restore, failover, worker-recovery and dependency-outage evidence.
- **v0.24 External Assurance Evidence** — hash-pinned metadata registry for independent security review, penetration testing and operational validation. Recording evidence does not self-certify Arbiter.
- **v0.25 Shadow Pilot Harness** — run Arbiter against real venue contracts without changing official venue resolution or settlement.
- **v0.26 Reference Exchange v2** — play-money YES/NO limit orders, complementary-contract matching, positions, settlement, order cancellation and audit.

See `ENTERPRISE_VALIDATION_PROGRAM.md`, `deploy/aws/README.md`, `SHADOW_PILOT_RUNBOOK.md`, and `docs/security/`.

### v0.26.1 Terraform validation patch
The AWS reference deployment was normalized to valid multi-line HCL and the release gate now includes an offline Terraform syntax-shape check. `terraform validate` remains the authoritative local/cloud validation step before planning or applying infrastructure.
