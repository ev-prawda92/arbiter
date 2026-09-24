# Arbiter API Coherence Test Plan

The API coherence harness validates that Arbiter's current surfaces agree on the same governed contract state.

## Canonical paths

1. **READY** — BLS CPI numeric threshold with exact clock/timezone and first-release rule.
   - Compiler: `READY`
   - Resolution without evidence: `PENDING`
2. **REVIEW** — Federal Reserve rate-cut event with a defined window but missing exact cutoff/timezone.
   - Compiler: `REVIEW`
   - Resolution: `HELD`
   - Gate: `COMPILER_REVIEW`
3. **BLOCK** — CPI title paired with government-shutdown rules.
   - Compiler: `BLOCK`
   - Resolution: `HELD`
   - Gate: `COMPILER_BLOCK`
   - BLS authority must not be trusted from the conflicting title.

## Durable workflow

The harness reruns the REVIEW case using the same `case_id`, verifies run history increments, and promotes the case to a reusable template.

## Cross-surface checks

The harness confirms these surfaces load after the test activity:

- health
- cases
- templates
- authorities
- infrastructure
- overview
- work queue
- portfolio
- policy
- developer manifest
- Swagger
- ReDoc
- OpenAPI

## Audit and benchmark

The harness requires the audit chain to verify and confirms coherence-harness activity appears in the audit log.

It also reruns the development benchmark and checks the current baseline:

- 90 total cases
- 90 valid cases
- 70 controlled mutations
- 20 clean parents
- defect detection rate 1.0
- clean false-positive rate 0.0

These benchmark checks are development/calibration regression checks, not an external accuracy claim.

## Run

With Arbiter running on port 8000:

```bash
python3 scripts/coherence_test.py
```

Alternate port:

```bash
python3 scripts/coherence_test.py --base-url http://127.0.0.1:8001
```

If API-key auth is enabled:

```bash
ARBITER_API_KEY='arb_your_key' python3 scripts/coherence_test.py
```

To avoid rerunning the benchmark and only inspect the latest result:

```bash
python3 scripts/coherence_test.py --skip-benchmark-run
```

The process exits with code `0` on full coherence and `1` if any check fails, making it suitable for CI later.
