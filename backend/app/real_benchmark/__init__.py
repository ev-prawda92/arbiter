"""Arbiter v0.27 real-world holdout benchmark package.

The benchmark is intentionally split into four phases:

1. collect candidate contracts from public venue APIs;
2. freeze an immutable dataset with labels physically separated from inputs;
3. run Arbiter blind against contract inputs only;
4. score the completed run after predictions are hash-pinned.

This separation is a benchmark-control mechanism. It is not independent
certification and does not make a production-settlement claim.
"""

BENCHMARK_VERSION = "0.27.0"
DATASET_SCHEMA = "arbiter.real-contract-holdout.v1"
PREDICTION_SCHEMA = "arbiter.real-contract-predictions.v1"
REPORT_SCHEMA = "arbiter.real-contract-report.v1"
