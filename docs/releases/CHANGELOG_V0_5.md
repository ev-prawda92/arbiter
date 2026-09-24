# Arbiter v0.5 — Resolution Benchmark Harness

## Benchmark infrastructure
- Added `backend/app/benchmark/` with schema, mutation generators, deterministic validators, metrics, and runner.
- Added `backend/data/benchmark/arb_gold_clean_v0_1.json` as the 20-case clean calibration set.
- Added controlled mutations for:
  - `SOURCE_MISSING`
  - `SOURCE_VAGUE`
  - `TIMEZONE_MISSING`
  - `SUBJECTIVE_TERM`
- Each mutation is validated before it is admitted to metrics.
- Lever attribution is measured by risk-score delta versus the clean parent, not by highest absolute risk score.

## Development benchmark result
Current calibration run:
- 90 total valid cases
- 20 real clean parent cases
- 70 controlled mutations
- 100% planted-defect detection on these four mutation classes
- 100% correct lever attribution on detected mutations
- 20/20 clean parents AUTO-RESOLVE
- 0 clean false positives

**Important:** These are development/calibration results, not an independent external accuracy claim. The 20 clean parents informed development. An untouched holdout set is required before publishing performance claims.

## Engine improvements exposed by evals
- Exact clock times now require a timezone even when the contract is otherwise release/event-triggered.
- Tightened official Tour de France source recognition so an event-name mention alone is not treated as a settlement source.
- Preserved deterministic source/timing/definition scoring and governed policy thresholds.

## API
- Version bumped to `0.5.0`.
- Added `GET /api/benchmark`.
- Added `GET /api/benchmark/cases`.
- Added `GET /api/benchmark/failures`.
- Added `POST /api/benchmark/run`.

## Frontend
- Added a Benchmark navigation item and benchmark dashboard.
- Dashboard shows eval case count, clean parent count, mutation count, defect detection, lever attribution, clean recognition, failure-mode coverage, and methodology boundaries.

## Validation
- Python backend compiles successfully.
- Benchmark runner executes successfully and writes `backend/data/benchmark/latest_results.json`.
- Benchmark API functions execute successfully.
- Frontend production build was not executed in this environment because Vite/node_modules are not installed. Source changes are included for normal local build validation.
