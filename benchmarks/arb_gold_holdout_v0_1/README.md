# ARB-GOLD-HOLDOUT-v0.1

This directory is intentionally **not frozen yet** in the release package.

Target: **50–100 untouched, already-resolved real event contracts** (default freeze target: 75).

The dataset is created only when a curator runs `scripts/freeze_holdout.py`. Once frozen, this directory contains:

- `contracts.jsonl` — blind contract inputs; no outcome/gold labels
- `evidence.jsonl` — independently frozen observations usable during blind resolution; no venue outcome labels
- `labels.jsonl` — exchange outcomes and optional independently reviewed gold labels
- `provenance.jsonl` — venue/source URL, retrieval time, raw payload hash
- `manifest.json` — file hashes, dataset hash, corpus distribution, benchmark controls
- `FROZEN.sha256` — aggregate dataset fingerprint
- `rejections.json` — candidate rows excluded during validation

## Non-negotiable benchmark rule

**Do not tune Arbiter against this holdout.** If the holdout exposes a weakness, record the result. Develop the fix against the development corpus and evaluate the change on a new future holdout version.

## Candidate sources

v0.27 ships collectors for:

- Kalshi public settled/historical market endpoints
- Polymarket Gamma closed-market endpoint

Collection is not freezing. Candidates should be inspected for provenance/rule completeness before the freeze step.
