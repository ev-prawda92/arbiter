# Diligence notes

This page is for a technical reviewer. It sets out what runs today, what is a reference
implementation, and what is not done yet.

## Verify it yourself

```bash
make install
make check        # lint, format, pytest, all 27 gates, release gate 452/452
./start.sh        # then open /console.html and /decision-workbench.html
```

Every gate starts from empty temporary state, so no result depends on a pre-seeded database.

## What is real

| Capability | Evidence |
|---|---|
| Live venue intake | `scripts/sync_venues.py` reads Kalshi and Polymarket public APIs. Two recorded scans (300 and 600 markets) are replayed offline in the gates (`tests/fixtures/venue_scan_*.json.gz`). |
| Hardness triage | On the most recent live scan, 22 of 500 open Kalshi markets (Sports excluded) and 3 of 100 Polymarket markets were flagged for human review. Each flag names the reason: interpretive criteria, multi-source conflict, revised source, or late/void. |
| Decision clearing | One recorded decision clears every case that shares its root cause. Blockers that must never be cleared automatically stay open. Covered by the decision clearing and propagation gates. |
| Audit trail | `audit_events` is a hash chain. The public API gate tampers with a row and checks that verification detects it. |
| Settlement signing | HMAC-signed packets. Production refuses to sign without `ARBITER_SETTLEMENT_SIGNING_SECRET` (tests in `tests/test_repo_consistency.py`). |
| Precedent engine | Decisions become precedent; new contracts are matched on arrival. On 838 real markets the same-template tier finds the template in another event for 79.6% of markets at 100% precision (`scripts/precedent_eval.py`). The precedent gate proves follow / distinguish / overrule, appeals and Ask Arbiter end to end. |
| Worked case | `demo/run_iran_case.py` runs a contested geopolitical contract through the real engine and records the output. |

## What is production-shaped but not deployed

- PostgreSQL adapter with row-level security and request-scoped tenants (`production_data.py`).
  Local runs use SQLite.
- OIDC federation foundation, scoped API keys, secrets custody interfaces.
- AWS deployment templates (`deploy/aws`). They have not been applied to a live account.
- Resilience primitives and recovery drills, exercised in-process only.

## What is a reference implementation

- `reference_exchange.py`: play-money exchange used to test the end-to-end flow. It is not a
  matching engine to run in production.
- `shadow_pilot.py`: harness for running Arbiter next to a partner's live process. No partner
  has used it yet.

## Known limits

- **Not certified for production settlement.** The benchmark report states
  `production_settlement_certified: false`. Certification needs an external security review,
  a penetration test (scope: `docs/security/PEN_TEST_SCOPE.md`) and resilience evidence from a
  real deployment.
- **Accuracy has not been benchmarked yet.** The blind holdout protocol (`ARB-GOLD-HOLDOUT-v0.1`)
  is specified and its tooling is gated, but the holdout set has not been collected and run.
  Current evidence is engineering validation, not measured resolution accuracy.
- **Triage recall is unmeasured.** The hardness classifier was tuned for precision on live
  scans. Markets it misses are not yet estimated.
- **Precedent thresholds come from two days of scans.** Real cross-event clause
  repeats in that data number two, both correct. Re-measure as scans accumulate.
  Ask Arbiter is retrieval over the record with a small declared lexicon, not a
  language model. It says when nothing covers a question.
- **Single-node.** No horizontal scaling or HA has been tested.
- **LLM features are advisory and off by default.** No outcome depends on a model.

## Data sources

Only public venue endpoints are used: Kalshi `external-api.kalshi.com` / `api.elections.kalshi.com` (trade-api v2)
market and event listings, and Polymarket Gamma. No authenticated trading APIs are used, and no
credentials are stored in the repository.

## Engineering practice

- One product version (`VERSION`), enforced across backend, frontend and API by tests.
- Pinned dependencies. Lint and format are enforced in CI.
- Every behavior change ships with a gate, and releases are recorded in `CHANGELOG.md`.
- Built with AI coding assistance under human direction. Nothing merges without `make check`
  passing.

## Ownership

Copyright (c) 2026 Operation Mincemeat LLC. All rights reserved. See `LICENSE`.
