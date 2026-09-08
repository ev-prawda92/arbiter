# Enterprise Readiness

## Current status — v0.21

Arbiter now has a production-shaped data plane, enterprise identity/secrets, a governed model gateway, a play-money reference exchange, application-level resilience controls, and an executable settlement-assurance harness. The complete local release stack passes **334/334 checks across 13 suites**.

This is **not production settlement certification**. v0.21 intentionally reports `production_settlement_certified: false`. Remaining certification evidence includes: a deployed managed production environment, external security architecture review, penetration test, untouched real-contract holdout, production load/concurrency testing, backup/restore and multi-zone failover drills, external observability/alerting, and an incident-response exercise.

## Implemented milestones

- v0.14 — Enterprise Identity & Tenant Boundary
- v0.15 — Production Reliability Foundation
- v0.16 — Governed Model Intelligence Gateway
- v0.17 — Production Data Plane
- v0.18 — Enterprise Secrets, Model Administration & OIDC
- v0.19 — Reference Exchange & End-to-End Settlement Harness
- v0.20 — Production Operations & Resilience
- v0.21 — Settlement Assurance Harness

## Certification boundary

Arbiter's internal gates demonstrate deterministic behavior, fail-closed controls, auditability, and repeatable validation. Independent certification requires evidence produced by external reviewers and by the deployed infrastructure itself.

## v0.26 validation status

Arbiter is enterprise-architected and pilot-ready, but remains **NOT_CERTIFIED**. The repository now contains deployment and validation machinery for the remaining proof steps. Actual enterprise-grade claims still require a provisioned cloud environment, deployed load/DR/failover results, independent security review and penetration test, a real venue shadow pilot, and externally reviewable evidence.
