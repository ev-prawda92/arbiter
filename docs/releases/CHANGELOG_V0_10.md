# Arbiter v0.10 — Enterprise Boundary & Exchange Profiles

- Production-default fail-closed authentication (`ARBITER_ENV=production`).
- Preferred hashed API-key records with per-key scopes (`ARBITER_API_KEY_RECORDS`).
- Backward-compatible legacy local API keys; disabled by default in production.
- Scoped authorization for contract, case, policy, authority, evidence, resolution, operations and benchmark mutations.
- Explicit production CORS allow-listing.
- Security headers and request correlation IDs.
- `/api/readiness` and `/api/security-posture` gates.
- Kalshi/DCM and Polymarket/UMA exchange profiles with explicit settlement-authority boundaries.
- Analyze/compile calls accept `exchange_profile` and preserve it in compilation metadata.
- Existing v0.9.5 coherence suite remains 48/48 passing.
- New `scripts/enterprise_gate.py` validates runtime boundary and exchange profiles.

This release is an enterprise control foundation, not a claim of production certification or completed security assurance.
