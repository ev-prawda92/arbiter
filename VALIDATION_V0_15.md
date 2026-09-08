# Arbiter v0.15 Validation

The v0.15 reliability gate validates the new application-level reliability contracts against a running Arbiter API.

Expected result:

```text
RESULT: 27/27 checks passed; 0 failed
PRODUCTION RELIABILITY GATE: PASS
```

The complete release runner should finish with:

```text
RELEASE GATE: PASS — 192/192 checks across 7 suites
```

The suite covers durable enqueue/claim/complete, lease ownership, retry/dead-letter behavior, idempotency replay and collision protection, signed webhook verification, replay rejection, migration presence, operational posture, audit continuity, and readiness continuity.

These tests are development assurance, not an external security certification or proof of settlement-production readiness.
