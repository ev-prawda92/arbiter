# Arbiter v0.16 — Governed Model Intelligence Gateway + Operator Copilot

## Added
- `backend/app/model_gateway.py` as the single governed entry point for external model usage.
- Preferred OpenAI Responses API integration with strict JSON-schema Structured Outputs.
- Configurable model tiers (`ARBITER_MODEL_DEFAULT`, `ARBITER_MODEL_FAST`) with GPT-6 Astra / GPT-5.6 Terra defaults.
- Anthropic compatibility path for existing deployments.
- Immutable prompt IDs and prompt versions for contract triage, semantic review, and case Copilot.
- Per-tenant daily call ceiling, maximum input size, output-token ceiling, timeout controls, and provider-storage control.
- Persistent `model_invocations` provenance registry with provider/model IDs, prompt version, input/output hashes, usage, latency, validation state, and response ID.
- Append-only `model.invocation.recorded` audit events.
- Model-gateway schema migration record (`v0.16-model-gateway`).
- Model posture endpoint and invocation registry.
- Deterministic no-provider self-test path for release validation.
- AI semantic-review endpoint grounded by Arbiter's deterministic semantic layer.
- Saved-case operator Copilot endpoint and frontend Copilot modal.
- Model Intelligence card in the Controls view.
- `ai:use` and `ai:read` authorization scopes.
- `scripts/model_gateway_gate.py` with 20 deterministic checks.
- Full release gate expanded to 212/212 checks across 8 suites.

## Security / authority boundary
- Model tools are disabled in v0.16.
- Contract, rule, and evidence text is explicitly treated as untrusted data.
- Model outputs are always labeled advisory/non-binding.
- Models cannot mutate case state, approve payouts, authorize settlement, or override deterministic resolution controls.
- External model availability is optional; Arbiter's binding control plane continues without an API key.

## Not included / not claimed
- No claim of production settlement certification.
- No external provider call is made by the deterministic release gate.
- Managed PostgreSQL, SSO, KMS/HSM, HA, external observability, pen testing, and real-contract holdout assurance remain future production-hardening work.
