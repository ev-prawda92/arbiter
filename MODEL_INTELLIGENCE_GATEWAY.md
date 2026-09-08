# Arbiter Model Intelligence Gateway — v0.16

## Principle
The model layer exists to make Arbiter easier to understand and more capable at interpreting complex language. It does not become the settlement authority.

**Model → interpretation / explanation**  
**Compiler + policy → governed specification**  
**Evidence → facts**  
**Deterministic engine → binding outcome**  
**Independent approval → settlement authorization**

## Why a gateway
Direct provider calls scattered throughout the application would make behavior, auditing, cost control, and model upgrades difficult to govern. v0.16 therefore routes external model use through one service with a fixed set of purposes and schemas.

## Purposes
### `contract_triage`
Backward-compatible second opinion on Source / Timing / Definition ambiguity.

### `semantic_review`
Frontier-model semantic analysis grounded by Arbiter's deterministic semantic output. It may propose clarifying questions and identify unresolved dimensions, but must not fabricate missing terms.

### `case_copilot`
Answers operator questions from a saved Arbiter case record only. It explains state, findings, and suggested next actions.

## OpenAI path
The OpenAI provider uses `POST /v1/responses`, sets `store` from `ARBITER_MODEL_PROVIDER_STORE` (false by default), applies a JSON Schema via `text.format`, and records the provider response ID/model ID and token usage.

No provider tools are supplied in v0.16.

## Environment variables
```bash
OPENAI_API_KEY=...
ARBITER_MODEL_PROVIDER=openai
ARBITER_MODEL_DEFAULT=gpt-6-astra
ARBITER_MODEL_FAST=gpt-5.6-terra
ARBITER_MODEL_REASONING_EFFORT=medium
ARBITER_MODEL_TIMEOUT_SECONDS=45
ARBITER_MODEL_MAX_OUTPUT_TOKENS=1800
ARBITER_MODEL_MAX_INPUT_CHARS=120000
ARBITER_MODEL_DAILY_MAX_CALLS=500
ARBITER_MODEL_PROVIDER_STORE=false
```

Anthropic compatibility:
```bash
ANTHROPIC_API_KEY=...
ARBITER_MODEL_PROVIDER=anthropic
ANTHROPIC_MODEL=claude-sonnet-4-6
```

## API examples
### Posture
`GET /api/model-gateway`

### Semantic review
```json
POST /api/ai/semantic-review
{
  "title": "Will U.S. CPI be above 3.0%?",
  "rules": "...",
  "model_tier": "default"
}
```

### Case Copilot
```json
POST /api/cases/{case_id}/copilot
{
  "question": "Why is this held and what needs to be fixed?",
  "model_tier": "default"
}
```

Every successful response includes:
- `invocation_id`
- structured `output`
- `provenance.provider`
- configured/provider model IDs
- prompt ID/version
- input/output hashes
- latency/token usage
- validation status
- explicit `authority.binding=false`

## Change governance
Any material prompt or structured-output schema change should increment its prompt version and run model regression tests before production deployment. Model aliases may move over time; v0.16 surfaces unpinned aliases as warnings. Settlement-sensitive production use should pin provider-fixed model versions where available and validate changes before promotion.
