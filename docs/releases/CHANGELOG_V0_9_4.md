# Arbiter v0.9.4 — Case Registry & Templates

## Operator workflow

- Every `/api/analyze` compiler/integrity run is now automatically persisted as an **Analysis Case**.
- Re-running a saved case appends a new immutable **Case Run** instead of overwriting prior results.
- Saved cases retain the exact market question, resolution criteria, compiler status, resolution outcome, timestamps, and latest run identity.
- Added a **Cases** workspace for recent contract work and reusable templates.
- Operators can reopen a saved case with its prior question and criteria prefilled, edit it, and rerun it without re-entering the contract from scratch.

## Templates

- Added persistent **Contract Templates**.
- Any saved case can be promoted to a reusable template.
- Starting from a template creates a new case while preserving the template provenance.
- Templates retain the question/rule structure but do not silently bypass compiler or control checks: every derived case is compiled and reviewed again.

## APIs

- `GET /api/cases`
- `GET /api/cases/{case_id}`
- `GET /api/templates`
- `POST /api/templates`
- `POST /api/cases/{case_id}/template`
- `POST /api/analyze` now accepts optional `case_id`, `source_template_id`, and `actor` and returns a `case` record.

## Auditability

- Case runs are append-only and store input/result hashes.
- Case-run and template creation events are written to the existing Arbiter hash-chained audit log.

## Product boundary

Templates accelerate repetitive market creation; they do not make a prior result authoritative for a new contract. Every new or modified contract still passes through the current compiler, integrity analysis, resolution gate, and governed controls.
