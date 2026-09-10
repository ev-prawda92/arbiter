# Arbiter Resolution API v1 Preview

Arbiter's public API is the external surface for governed real-world contract resolution. It is intentionally narrower than the internal application API.

## Product boundary

The v1 preview is **resolution infrastructure, not settlement authority**. It compiles contract language, evaluates frozen/explicit evidence, returns `YES`, `NO`, or `HOLD`, persists an auditable result, and exposes integrity hashes. A `HOLD` means the governed system refused to guess.

Default public mode is `sandbox`. The mode is surfaced in the `X-Arbiter-Mode` response header and `/health` response.

## Run locally

```bash
cd backend
python3 -m uvicorn app.public:app --host 0.0.0.0 --port 8001
```

Interactive documentation is available at `/docs`; OpenAPI is at `/openapi.json`.

## Authentication

The public API reuses Arbiter's existing API-key and OIDC authorization system.

Preferred header:

```text
X-Arbiter-Key: <key>
```

Production should use hashed key records through `ARBITER_API_KEY_RECORDS` or configured OIDC. Scopes are enforced per operation.

## Idempotency

`POST /v1/contracts/resolve` accepts:

```text
Idempotency-Key: <unique request key>
```

Reusing the same key with the same request returns the original result. Reusing it with a different request returns a conflict.

## Rate limits

The standalone public API has a sliding-window rate limiter. Configure requests per minute with:

```bash
export ARBITER_PUBLIC_RATE_LIMIT_PER_MINUTE=120
```

This in-process limiter is appropriate for the preview/sandbox service. A multi-instance production deployment should move enforcement to the gateway or a shared rate-limit store.

## Endpoints

### `POST /v1/contracts/compile`

Compile natural-language contract terms into Arbiter's governed resolution specification.

Request:

```json
{
  "contract_id": "market-123",
  "title": "Will CPI be at least 3.0%?",
  "rules": "Resolves YES if the official BLS CPI release reports year-over-year CPI at or above 3.0% for the specified month.",
  "contract_version": 1,
  "exchange_profile": "generic",
  "metadata": {}
}
```

The response includes the compiler status and a SHA-256 fingerprint of the compilation artifact.

### `POST /v1/contracts/resolve`

Compile and deterministically evaluate the contract against supplied evidence.

Request:

```json
{
  "contract_id": "market-123",
  "title": "Will CPI be at least 3.0%?",
  "rules": "Resolves YES if the official BLS CPI release reports year-over-year CPI at or above 3.0% for the specified month.",
  "evidence": {
    "observed_value": 3.1,
    "unit": "%",
    "authority": "BLS",
    "source_url": "https://example.gov/source",
    "retrieved_at": "2026-09-09T20:00:00Z",
    "raw_sha256": "sha256:..."
  }
}
```

Representative response:

```json
{
  "api_version": "v1",
  "resolution_id": "vres_...",
  "contract_id": "market-123",
  "verdict": "YES",
  "governance_status": "READY",
  "evidence_status": "SUFFICIENT",
  "requires_human_review": false,
  "resolution_method": "numeric-threshold-v1",
  "reason": "...",
  "compiled_spec_sha256": "sha256:...",
  "evidence_sha256": "sha256:...",
  "policy_version": "...",
  "created_at": "...",
  "request_sha256": "sha256:...",
  "response_sha256": "sha256:..."
}
```

### `GET /v1/resolutions/{resolution_id}`

Retrieve a persisted resolution and its pinned request/response hashes.

### `GET /v1/evidence/{resolution_id}`

Retrieve the evidence supplied for a public resolution, along with its evidence fingerprint.

### `POST /v1/contracts/verify`

Verify that a resolution exists and optionally compare its pinned response hash with a caller-supplied expected hash.

### `GET /v1/audit/{resolution_id}`

Return Arbiter's audit-chain verification result and events associated with the public resolution.

## Governance behavior

Arbiter does not force a binary answer. The public API returns `HOLD` when:

- the compiler is not `READY`;
- evidence is absent;
- evidence cannot be deterministically evaluated;
- the compiled definition type is unsupported;
- required semantics remain unresolved.

The governing principle remains:

> AI interprets. Policy governs. Evidence proves. Deterministic logic resolves. Humans handle exceptions.

## Production path

Before calling this production-grade public infrastructure, the preview still needs externally validated deployment, shared/global rate limiting, managed queue/webhook delivery, independent security testing, production key custody, observability, HA/failover testing, and an untouched reportable real-contract benchmark.
