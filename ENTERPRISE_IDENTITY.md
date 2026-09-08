# Enterprise Identity & Tenant Boundary

Arbiter v0.14 introduces a principal-bound tenant context.

Production API-key records should have:

```json
{
  "id": "market-ops-service",
  "sha256": "<sha256-of-secret>",
  "scopes": ["evidence:write", "resolution:write"],
  "tenant_id": "exchange-acme",
  "principal_id": "svc:market-ops",
  "principal_type": "service"
}
```

The authenticated principal owns its tenant context. A non-admin principal cannot request a different tenant using `X-Arbiter-Tenant`.

## Current boundary
- tenant/principal registry: implemented
- scoped service identities: implemented
- principal-bound request context: implemented
- production metadata gate: implemented
- database row-level security: future production data adapter
- OIDC/SAML/SCIM: future federation layer
- KMS/HSM key custody: future production secret/signing layer
