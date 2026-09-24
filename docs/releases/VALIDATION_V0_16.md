# Arbiter v0.16 Validation

## Deterministic model intelligence gate
`python3 scripts/model_gateway_gate.py --base-url http://127.0.0.1:8000`

Expected:
**20/20 PASS**

The suite verifies:
- v0.16 API surface;
- model-gateway posture;
- provider readiness declaration;
- configured model IDs;
- no model tools;
- advisory authority boundary;
- internal no-provider self-test;
- zero settlement authority;
- prompt identity/version provenance;
- input/output hashes;
- structured-output validation;
- advisory output marker;
- persistent invocation registry;
- non-binding metadata;
- infrastructure/developer manifest integration;
- audit event creation;
- audit-chain integrity.

## Complete release gate
`python3 scripts/release_gate.py --base-url http://127.0.0.1:8000`

Reference result during v0.16 build:
**RELEASE GATE: PASS — 212/212 checks across 8 suites**

## Important limitation
The release gate intentionally does not spend money or depend on external provider uptime. It validates the gateway's deterministic provenance, policy, audit, and schema plumbing through an internal self-test. A deployment that enables OpenAI/Anthropic must separately run provider integration tests using its own credentials and approved data-handling configuration.
