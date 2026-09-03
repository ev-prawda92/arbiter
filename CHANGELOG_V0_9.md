# Arbiter v0.9 — Developer Platform + Resolution Compiler

## Resolution Compiler v0.1

- Added `POST /api/compile` to convert natural-language market rules into a proposed `arbiter.resolution-spec.v1` object.
- Compiler emits field-level provenance, unresolved fields, control results, READY / REVIEW / BLOCK status, compiler version, and a canonical SHA-256 compilation hash.
- Compiler is conservative by design: missing authorities, timing, objective conditions, precedence, and revision policy are surfaced rather than invented.
- Added `POST /api/compile-and-create`, which persists a contract only when compilation status is READY.
- Contract Intelligence UI now runs the compiler alongside the existing Source / Timing / Definition review and exposes the proposed machine-readable specification.

## Developer platform

- FastAPI Swagger UI at `/docs`.
- ReDoc reference at `/redoc`.
- OpenAPI schema at `/openapi.json`.
- `GET /api/developer` exposes developer-platform capabilities and auth state.
- Added optional API-key protection for write/compile endpoints through `ARBITER_API_KEYS` and the `X-Arbiter-Key` header. Local development remains open when no keys are configured.
- Added developer quickstart and curated API reference under `docs/`.
- Added a dependency-free Python SDK preview under `sdk/python/`.
- Added a webhook event catalog for the next integration phase; delivery/registration is not implemented yet.

## Existing system preserved

- v0.8 Executive Overview and Work Queue remain intact.
- v0.7 portfolio intelligence remains read-only.
- v0.6 contract, authority, evidence, resolution-run, controls, and audit infrastructure remain the governed core.
- Existing 90-case development benchmark remains unchanged and passes after v0.9 changes.

## Boundary

Compiler and agent output are advisory proposals. They may structure, triage, explain, and recommend, but do not silently alter binding settlement outcomes.
