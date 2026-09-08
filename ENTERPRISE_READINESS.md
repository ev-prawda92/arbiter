# Arbiter Enterprise / Production Readiness

## Current status — v0.17
Arbiter now has a broad **application-level enterprise and production-data foundation**: scoped authentication, exchange profiles, active evidence infrastructure, maker-checker settlement authorization, governed policy, semantic contract intelligence, tenant/principal identity primitives, durable jobs/idempotency/webhook reliability, a governed model intelligence gateway, and a PostgreSQL/S3-oriented production data plane.

That is **not the same as production settlement certification**. v0.17 implements the application-side database, tenant-isolation, immutable evidence-storage, concurrency, and recovery hooks, but certification requires a provisioned production environment and independent assurance evidence that cannot be proven by the local application test suite alone.

## Completed application foundations
- v0.10 — Enterprise Boundary & Exchange Profiles
- v0.11 — Active Evidence Infrastructure
- v0.12 — Approval & Settlement Control
- v0.13 — Semantic Contract Intelligence
- v0.14 — Enterprise Identity & Tenant Boundary
- v0.15 — Production Reliability Foundation
- v0.16 — Governed Model Intelligence Gateway + Operator Copilot
- v0.17 — Production Data Plane

## v0.17 data-plane foundation now implemented
- SQLite local/reference backend plus PostgreSQL production adapter;
- PostgreSQL request-scoped tenant/principal context;
- DB-enforced tenant RLS with FORCE RLS and write `WITH CHECK` policies;
- fail-closed pre-v0.17 tenant-ownership migration;
- transaction/concurrency serialization for settlement packet creation;
- content-addressed raw evidence object storage;
- local and S3 object-store adapters;
- production configuration gates for PostgreSQL/TLS and managed object storage;
- local online backup + checksum/integrity verification;
- managed PostgreSQL snapshot/PITR recovery requirements;
- 28-check data-plane gate and 240-check full release gate.

## Remaining path to production-certified settlement infrastructure
### v0.18 — Enterprise Identity, Secrets & Key Custody
- OIDC/SAML SSO;
- organization/role mapping and fine-grained RBAC;
- service-account lifecycle and key rotation;
- in-product governed model/provider credential administration;
- external secrets manager;
- KMS/HSM-backed asymmetric signing for settlement artifacts and webhooks.

### v0.19 — Production Operations & Resilience
- deploy managed PostgreSQL and object storage in the target cloud/environment;
- connection/runtime tuning and pool sizing;
- managed workers/queues;
- centralized logs, metrics, and traces;
- SLOs and alerts;
- HA/failover architecture;
- measured recovery objectives and DR drills;
- load, concurrency, soak, and chaos/failure testing.

### v0.20 — Independent Settlement Assurance
- dependency/SAST/DAST/container review;
- threat model and architecture review;
- independent penetration test;
- incident-response tabletop and recovery evidence;
- two-tenant PostgreSQL isolation test suite;
- backup/PITR restore evidence from the deployed environment;
- untouched real-contract holdout;
- adversarial/dispute corpus;
- model regression suite and prompt/model change controls;
- buyer/venue-specific integration diligence.

### v1.0 — Production Settlement Candidate
Exit only when Arbiter can safely receive a governed contract, monitor authoritative evidence, deterministically produce a resolution outcome, route exceptions for independent approval, and hand off a signed auditable settlement authorization under tested production infrastructure — with external assurance evidence supporting the claim.

## Model-specific production requirements
Frontier models remain advisory. Production AI use should add:
- provider/data-retention review;
- fixed/pinned model IDs where the provider supports them;
- prompt/schema change approval;
- model-output regression testing;
- red-team/prompt-injection testing on hostile contract/evidence text;
- privacy/data-classification controls;
- cost/rate-limit/availability fallback policy;
- explicit proof that model unavailability cannot bypass deterministic settlement-critical functions.
