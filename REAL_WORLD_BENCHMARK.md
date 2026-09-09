# Arbiter v0.27 — Real-World Resolution Benchmark

## Purpose

v0.27 adds the machinery for a credible **untouched real-contract holdout** rather than extending the product with another speculative feature.

The benchmark answers two different questions without conflating them:

1. **Contract intelligence:** How does Arbiter interpret and gate real exchange contracts it did not help author?
2. **Outcome resolution:** When an independent evidence pack exists, does Arbiter reproduce the final YES/NO outcome without seeing the venue label?

The second question is scored only where evidence coverage exists. Arbiter does not guess missing evidence.

## Benchmark protocol

### 1. Collect candidates

```bash
python3 scripts/collect_holdout_candidates.py \
  --venue kalshi \
  --venue polymarket \
  --limit-per-venue 100 \
  --out benchmarks/candidates_v0_1.jsonl
```

Candidate collection is not a benchmark result. The collector preserves original title/rules fields, venue identity, result label, source URL, retrieval time, and a SHA-256 hash of the raw market object.

### 2. Curate before freezing

Review candidates for:

- verbatim/usable resolution criteria
- resolved binary outcome
- source provenance
- duplicate markets
- pathological templates or empty rule text
- reasonable domain mix

Do not run Arbiter on the candidate file before the frozen selection is created if the goal is a true untouched holdout.

### 3. Freeze

```bash
python3 scripts/freeze_holdout.py \
  benchmarks/candidates_v0_1.jsonl \
  --target 75 \
  --out benchmarks/arb_gold_holdout_v0_1
```

Freezing creates physically separate files:

```text
contracts.jsonl     # blind contract input; no outcome/gold labels
evidence.jsonl      # independent observations; no venue outcome labels
labels.jsonl        # venue outcome + optional independent gold labels
provenance.jsonl    # retrieval provenance + raw hashes
manifest.json       # all hashes + dataset metadata
FROZEN.sha256       # aggregate fingerprint
```

A frozen dataset cannot be overwritten by the freeze tool. Create `ARB-GOLD-HOLDOUT-v0.2` rather than editing v0.1.

### 4. Verify

```bash
python3 scripts/verify_holdout.py benchmarks/arb_gold_holdout_v0_1
```

Verification checks file hashes, aggregate dataset hash, case alignment, duplicate IDs, frozen marker, and label leakage into contract inputs.

### 5. Run blind

```bash
python3 scripts/run_holdout.py benchmarks/arb_gold_holdout_v0_1
```

The blind runner deliberately loads only `contracts.jsonl` plus the separately frozen `evidence.jsonl`. It never opens `labels.jsonl` during prediction. It records:

- Semantic Contract Intelligence status
- compiler READY / REVIEW / BLOCK status
- unresolved binding fields
- deterministic source/timing/definition risk scores
- engine verdict
- semantic and compilation hashes
- deterministic YES / NO / HOLD outcome, when the compiled contract and frozen evidence are sufficient
- evidence source/hash references and deterministic resolution trace

It does **not** read `labels.jsonl`. Non-READY contracts, missing evidence, and unsupported definitions resolve to **HOLD** rather than a guessed YES/NO.

### 6. Score only after predictions are pinned

```bash
python3 scripts/generate_benchmark_report.py \
  benchmarks/arb_gold_holdout_v0_1 \
  backend/data/real_benchmark_runs/<run-id>
```

The scorer loads labels only after the blind prediction artifact and run manifest have their own SHA-256 fingerprints.

## Metrics

Always available on a frozen real-contract corpus:

- READY / REVIEW / BLOCK distribution
- semantic status distribution
- source/timing/definition risk distribution
- unresolved-field frequency
- venue/category coverage

Available only when separately frozen human/independent gold labels exist:

- contract-status accuracy
- false-hold rate on gold READY cases
- ambiguity recall
- source/timing/definition agreement

Available only from the separately frozen evidence pack:

- evidence coverage
- deterministic YES/NO resolution coverage
- governed HOLD rate
- outcome agreement conditional on resolved YES/NO cases

Missing coverage remains `null` / unscored. It is never backfilled from Arbiter's own output.

## Product boundary

The benchmark is validation infrastructure, not a certification mechanism. Passing it does not establish regulatory compliance, production settlement certification, independent security assurance, or production operational readiness.

The governing principle remains:

> AI interprets. Policy governs. Evidence proves. Deterministic logic resolves. Humans handle exceptions.
