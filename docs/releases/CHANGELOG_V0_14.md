# Arbiter v0.14 — Enterprise Identity & Tenant Boundary

v0.14 adds the next enterprise deployment foundation without claiming full multi-tenant production certification.

## Added
- Principal-bound tenant context for authenticated API-key records.
- Human and service principal types.
- Tenant registry and principal registry.
- `/api/identity/whoami` and `/api/identity/posture`.
- Admin tenant/principal APIs.
- Production fail-closed validation for incomplete principal metadata.
- Production data guardrail requiring `ARBITER_DATABASE_BACKEND=postgresql`.
- `scripts/identity_gate.py` and inclusion in the complete release gate.

## Security boundary
This release establishes identity and tenancy control-plane primitives. It does **not** claim database row-level security or SSO certification. The production Postgres adapter, database-enforced tenant isolation, OIDC/SAML federation, KMS/HSM keys, and independent security testing remain required before settlement-critical deployment.
