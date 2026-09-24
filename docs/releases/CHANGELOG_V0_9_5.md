# Arbiter v0.9.5 — Automated Coherence Harness

## Added

- `tests/fixtures/coherence_cases.json` — version-controlled READY / REVIEW / BLOCK canonical cases.
- `scripts/coherence_test.py` — dependency-free HTTP smoke/regression harness against a running Arbiter API.
- `COHERENCE_TEST_PLAN.md` — release-gate expectations and commands.

## Coverage

The harness checks compiler/resolution gate coherence, durable case reruns, run history, template creation, cross-surface API availability, developer docs, audit-chain integrity, and the current development benchmark baseline.

## Boundary

The harness creates test cases and templates in the configured Arbiter database. Use a test database in CI or production-like environments.
