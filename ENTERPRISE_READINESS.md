# Arbiter Enterprise Readiness Roadmap

## v0.10 boundary established
Arbiter v0.10 adds production-default authentication, scoped API-key authorization, explicit CORS allow-listing, security headers, request correlation IDs, readiness/configuration gates, and explicit exchange settlement profiles.

This is an enterprise **foundation**, not a security certification.

## Production requirements still open
1. PostgreSQL with managed migrations, transaction isolation, connection pooling and HA.
2. SSO/OIDC/SAML and organization-level RBAC; service accounts and key rotation.
3. Secrets manager / KMS and encryption controls for credentials and sensitive configuration.
4. Durable queue/worker architecture for evidence polling, retries, backoff and idempotent jobs.
5. Multi-tenant data model, tenant isolation tests and per-tenant encryption/access policy.
6. Signed webhooks, replay protection and outbound delivery retry ledger.
7. Central logs/metrics/traces, source-health SLOs, alerting and incident runbooks.
8. Backup/restore drills, disaster recovery targets and region/availability design.
9. Dependency/SAST/DAST/container scanning, threat model, independent penetration test.
10. Maker-checker approvals and separation of duties for production settlement authorization.
11. Untouched holdout benchmark and adversarial resolution corpus.
12. Formal assurance package mapping tested controls to claims actually supported by evidence.

## Recommended build order
v0.10 Enterprise Boundary → v0.11 Active Evidence Workers → v0.12 Approval/Settlement Gate → v0.13 Production Data/Auth → v0.14 Observability/DR → v0.15 Security & Holdout Assurance.
