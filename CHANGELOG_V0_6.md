# Arbiter v0.6 — Resolution Control Infrastructure

## Domain core

Added four persistent, machine-readable resolution primitives:

- **ResolutionSpecification** — version-pinned canonical contract semantics.
- **Authority** — governed resolution source/version registry.
- **EvidenceRecord** — append-only normalized observation with provenance and hashes.
- **ResolutionRun** — replayable execution linking contract, policy, engine, evidence, controls, outcome, exceptions, and approvals.

## Trust & governance

- SQLite-backed reference ledger with WAL mode and foreign-key enforcement.
- Append-only hash-chained audit events.
- Audit-chain verification endpoint.
- Domain object hashes for contract specs, authorities, evidence records, and resolution runs.
- Reference authorities for BLS CPI, Federal Reserve FOMC, and NOAA/NWS.
- Resolution control library (`RES-001` through `RES-008`).
- Block-vs-review control semantics.

## API

- `GET /api/infrastructure`
- `GET/POST /api/contracts`
- `GET /api/contracts/{contract_id}/resolution-spec`
- `GET/POST /api/authorities`
- `GET/POST /api/evidence`
- `GET/POST /api/resolution-runs`
- `GET /api/audit`

## Reuse from Cortex

v0.6 adapts Cortex production design patterns rather than merging Cortex wholesale:
version-pinned state, append-oriented run history, governed sources, durable persistence,
and auditable control-plane events. Secrets/auth/tenancy/observability remain staged for a
later production-hardening pass.

## Boundary

The control library provides technical governance controls. It does not assert that use of
Arbiter, by itself, makes an exchange legally or regulatorily compliant.
