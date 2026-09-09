# Arbiter v0.27.0 — Real-World Resolution Benchmark

v0.27 moves Arbiter from primarily internal engineering validation toward untouched real-world contract proof.

## Added

- `backend/app/real_benchmark/`
  - public venue candidate normalizers/collectors
  - immutable holdout freezer
  - label-leakage detection
  - deterministic stratified selection
  - dataset verification and hash pinning
  - blind Arbiter runner
  - deterministic compiled-spec + frozen-evidence resolver
  - governed YES / NO / HOLD resolution path
  - post-run scoring and Markdown/JSON reporting
- `scripts/collect_holdout_candidates.py`
- `scripts/freeze_holdout.py`
- `scripts/verify_holdout.py`
- `scripts/run_holdout.py`
- `scripts/generate_benchmark_report.py`
- `scripts/real_benchmark_gate.py`
- `/api/real-benchmark` posture endpoint
- `/api/real-benchmark/verify`
- `/api/real-benchmark/run`
- corrected the stale OpenAI default model identifier to `gpt-5.6-sol` while retaining `gpt-5.6-terra` as the fast tier
- Benchmark UI now distinguishes development calibration from the untouched real-contract program.
- `benchmarks/arb_gold_holdout_v0_1/` program directory and source plan.

## Benchmark controls

- outcome/gold labels physically separated from blind contract inputs
- frozen files individually SHA-256 pinned
- aggregate dataset fingerprint
- frozen dataset overwrite blocked
- evidence physically separated from venue/gold labels and independently SHA-256 pinned
- prediction artifact hash-pinned before labels are opened for scoring
- explicit `labels_loaded_during_run: false` run attestation
- run manifest pins both contract and evidence hashes
- non-READY / missing-evidence cases HOLD rather than guessing
- no-tuning-on-holdout policy
- missing evidence/gold coverage remains unscored rather than inferred

## Scope boundary

v0.27 provides the benchmark **protocol and executable infrastructure**. The release package does not pretend that ARB-GOLD-HOLDOUT-v0.1 is already populated. The next real-world validation action is to collect, curate, and freeze 50–100 untouched resolved contracts.

Production settlement certification remains false.
