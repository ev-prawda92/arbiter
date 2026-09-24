# Arbiter v0.34 — Governed Decision Records

v0.34 turns the human judgment inside the Case Workspace into a first-class domain object.

## Product goal

Arbiter should reduce a large exception queue to the smallest number of defensible human decisions, record those judgments once, and reuse them safely when re-evaluating dependent cases.

## New core primitive

`arbiter.decision-record.v1`

A Decision Record captures:

- decision type and exact question;
- operator selection and rationale;
- affected cases / cluster / contract;
- governing rule;
- controlling authorities and evidence;
- policy basis;
- precedent references;
- actor and timestamp;
- supersession relationship;
- canonical SHA-256 hash;
- hash-chained audit event.

Decision records are deliberately non-binding by themselves. They cannot mutate contract terms, evidence, YES/NO/HOLD outcomes, or settlement authorization. They are governed inputs to subsequent re-evaluation.

## v0.34 build sequence

1. Durable Decision Record domain + storage.
2. API endpoints for create/read/list/precedent retrieval.
3. Structured decision action in Case Workspace.
4. Bind one cluster decision to all affected cases where policy permits.
5. Re-run governed evaluation after a decision is recorded.
6. Show before/after workload compression.
7. Feed decision records into contextual Ask Arbiter and precedent retrieval.

## Release gate

Run:

```bash
python3 scripts/decision_record_gate.py
```

The gate verifies durable round-trip storage, canonical hashing, supersession, deterministic precedent candidates, hash-chained audit integrity, and fail-closed decision-type validation.

## North-star behavior

> 100 unresolved cases → 4 irreducible human decisions → record each once → re-evaluate all dependent cases → safely clear everything the new governed judgment resolves.
