# Arbiter v0.27 — Product / Technical Manifest

## Product thesis
Arbiter is semantic contract intelligence and resolution infrastructure for event markets. It converts natural-language market rules into governed resolution specifications, monitors authoritative evidence, executes deterministic resolution logic, controls approvals and settlement authorization, and preserves an auditable record.

> **AI interprets. Policy governs. Evidence proves. Deterministic logic resolves. Humans handle exceptions.**

## Current platform layers
1. **Semantic Contract Intelligence** — identifies domain concepts, missing definitions, timing ambiguity, authority ambiguity, and clarification questions.
2. **Resolution Compiler** — converts sufficiently specified rules into machine-readable `ResolutionSpecification` objects and returns READY / REVIEW / BLOCK.
3. **Contract & Authority Control** — versioned contracts, governed authorities, control library, and policy state.
4. **Active Evidence Infrastructure** — monitors, normalized observations, immutable raw payload objects, revisions, conflicts, outages, retries, source health, and reevaluation requests.
5. **Deterministic Resolution** — binding resolution logic is version-pinned and evidence-driven.
6. **Approval & Settlement Control** — maker-checker approvals and signed, idempotent settlement authorization packets with venue-specific handoff semantics.
7. **Enterprise Identity & Tenant Boundary** — tenant/principal registry, scoped API keys, production fail-closed identity metadata checks.
8. **Production Reliability Foundation** — durable jobs, leases, retries, dead-letter handling, idempotency, signed webhooks, replay protection, and migration tracking.
9. **Governed Model Intelligence Gateway** — provider abstraction, structured outputs, prompt versioning, usage limits, provenance, audit logging, and operator Copilot.
10. **Production Data Plane (v0.17)** — PostgreSQL adapter, request-scoped tenant context, database RLS, content-addressed evidence objects, settlement serialization, and backup/restore verification hooks.
11. **Real-World Resolution Benchmark (v0.27)** — untouched contract collection/freeze protocol, physical label separation, blind execution, hash-pinned predictions, post-run scoring, and no-tuning-on-holdout controls.

## v0.17 data-plane APIs
- `GET /api/data-plane` — production data-plane posture.
- `POST /api/data-plane/self-test` — deterministic object/SQL/RLS/context self-test.
- `POST /api/data-plane/backup` — local SQLite online backup or production backup-plan response.
- `POST /api/data-plane/backup/verify` — local checksum + SQLite integrity verification.

## Production data-plane configuration
```bash
export ARBITER_ENV=production
export ARBITER_DATABASE_BACKEND=postgresql
export ARBITER_DATABASE_URL='postgresql://...'
export ARBITER_DATABASE_SSLMODE=require
export ARBITER_OBJECT_STORE_BACKEND=s3
export ARBITER_S3_BUCKET='...'
export ARBITER_S3_PREFIX='arbiter'
```

Production additionally requires the existing authentication, identity, settlement-signing, webhook-signing, and CORS controls.

## Model boundary
Models are **advisory only**. They may interpret, summarize, explain, classify, propose clarifying questions, and assist operators. They do not change contract/policy state, determine a binding settlement outcome, approve payout, or authorize settlement.

Current OpenAI defaults are configurable:
```bash
export ARBITER_MODEL_PROVIDER='openai'
export ARBITER_MODEL_DEFAULT='gpt-5.6-sol'
export ARBITER_MODEL_FAST='gpt-5.6-terra'
```

## Release validation
`python3 scripts/release_gate.py`

Expected v0.17 reference result:

**RELEASE GATE: PASS — 240/240 checks across 9 suites**

Suites:
- coherence: 48
- enterprise boundary: 14
- active evidence: 27
- settlement control: 30
- semantic contract: 29
- identity & tenant: 17
- reliability: 27
- model intelligence: 20
- production data plane: 28

This validates internal release coherence in the reference environment. It does **not** certify security, regulatory compliance, availability, or live settlement fitness.

## Production certification gaps
Before Arbiter can credibly be labeled production-certified settlement infrastructure, the following remain open:
- deploy and validate actual managed PostgreSQL and managed object storage;
- rehearse production migrations and rollback;
- test two-tenant isolation against real PostgreSQL;
- enterprise SSO/OIDC/SAML and mature RBAC;
- secrets manager and KMS/HSM-backed signing;
- managed durable queue/runtime;
- HA/failover and disaster recovery;
- centralized logs/metrics/traces, SLOs, alerts, incident runbooks;
- backup/PITR restore drill in the deployed environment;
- load, concurrency, soak, and chaos/failure testing;
- dependency/SAST/DAST/container review;
- independent architecture/security review and penetration test;
- untouched real-contract holdout and adversarial/dispute set;
- venue-specific integration diligence/certification.

## Primary code locations
- `backend/app/main.py` — FastAPI application and API surfaces.
- `backend/app/semantic_contract.py` — deterministic semantic intelligence.
- `backend/app/compiler.py` — resolution compiler.
- `backend/app/resolution_infra.py` — persistent control-plane domain store and audit chain.
- `backend/app/active_evidence.py` — active evidence monitoring and raw evidence object references.
- `backend/app/approval_control.py` — approval and settlement authorization.
- `backend/app/identity_tenant.py` — enterprise tenant/principal boundary.
- `backend/app/reliability.py` — durable reliability primitives.
- `backend/app/model_gateway.py` — governed model gateway and prompt/schema registry.
- `backend/app/production_data.py` — PostgreSQL/RLS/object-storage/backup data plane.
- `frontend/src/main.jsx` — operator/executive UI and Copilot modal.
- `scripts/release_gate.py` — complete release gate.


## v0.18
- `backend/app/enterprise_secrets.py` — secret custody and tenant model-provider administration
- `backend/app/identity_federation.py` — OIDC enterprise identity foundation
- `scripts/enterprise_secrets_gate.py` — v0.18 validation suite
- `ENTERPRISE_SECRETS_AND_FEDERATION.md` — security/identity design notes


## v0.19–v0.21 additions

11. **Reference Exchange (v0.19)** — play-money contract-to-settlement integration harness; no real-money custody or production matching engine.
12. **Production Operations & Resilience (v0.20)** — dependency health, admission/backpressure, incident lifecycle, and recovery drill evidence.
13. **Settlement Assurance (v0.21)** — adversarial suite, frozen holdout datasets, hash-pinned reports, and explicit certification blockers.

Expected v0.21 local reference result:

**RELEASE GATE: PASS — 334/334 checks across 13 suites**

This result is internal release validation and does not represent external security certification or regulatory approval.

## Enterprise validation extensions (v0.22–v0.26)

13. **Cloud Deployment Foundation (v0.22)** — Docker + AWS IaC and deployment preflight.
14. **Resilience Validation Lab (v0.23)** — local stress/failure scenarios and deployed evidence registry.
15. **External Assurance Evidence (v0.24)** — independent review/test metadata with SHA-256 fingerprints.
16. **Shadow Pilot Harness (v0.25)** — real-contract, zero-settlement-authority design-partner workflow.
17. **Reference Exchange v2 (v0.26)** — play-money order book/matching and end-to-end settlement sandbox.


## v0.27 real-world benchmark

18. **ARB-GOLD-HOLDOUT-v0.1** — default target 75 already-resolved real contracts, with 50–100 accepted as the initial proof range.
19. **Blind benchmark execution** — `contracts.jsonl` is processed without opening `labels.jsonl`; prediction artifacts are hash-pinned before scoring.
20. **Coverage-aware scoring** — contract-quality accuracy requires separately frozen human/independent labels; outcome agreement requires evidence-backed predictions. Missing coverage is reported as unscored.

Expected v0.27 local reference result:

**RELEASE GATE: PASS — 452/452 checks across 18 suites**

The v0.27 release package includes the benchmark machinery but intentionally does not claim ARB-GOLD-HOLDOUT-v0.1 is already populated. Real contract collection and freeze is the next validation action.
