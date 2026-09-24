# Arbiter v0.18 — Enterprise Secrets, Model Administration & Identity Federation

v0.18 moves model credentials and enterprise identity closer to a production control plane.

## Added
- Tenant-governed model-provider administration for OpenAI and Anthropic.
- Write-only provider credential API: raw secrets are accepted once and never returned by Arbiter APIs.
- Local development secret custody using Fernet encryption with a local master key excluded from source control.
- Production secret-custody adapter for AWS Secrets Manager with optional customer-managed KMS key.
- Provider connect/rotate/disable workflows and masked credential metadata.
- Tenant-scoped model policy: default model, fast model, allowed AI purposes, and daily call limits.
- Model Gateway credential resolution now prefers tenant-administered provider configuration, with environment variables as a development/backwards-compatible fallback.
- OIDC bearer-token federation foundation with issuer, audience, JWKS, tenant/principal claim mapping, scope mapping, and signature validation.
- Infrastructure UI: Models & Credentials admin panel.
- `GET /api/model-providers`
- `POST /api/model-providers`
- `POST /api/model-providers/{provider}/disable`
- `GET /api/enterprise-secrets`
- `POST /api/enterprise-secrets/self-test`
- `GET /api/identity/federation`
- `POST /api/identity/federation/self-test`
- New release gate: `scripts/enterprise_secrets_gate.py`.

## Authority boundary
Provider configuration and frontier-model access remain advisory only. No model credential, model output, or OIDC identity grants settlement authority by itself. Binding settlement remains governed by deterministic contract logic, authoritative evidence, approval policy, and settlement authorization controls.

## Production boundary
This release adds production-capable adapters and fail-closed configuration posture. Live production certification still requires provisioned cloud secrets/KMS, a real identity provider, managed PostgreSQL/object storage, operational resilience testing, and independent security assurance.
