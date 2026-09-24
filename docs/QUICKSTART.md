# Arbiter v0.17 Quick Start

## Run locally
```bash
cd Arbiter
./start.sh
```
Then open **http://localhost:8000**.

Local development uses SQLite and a local content-addressed object store by default.

## Run the release gate
With the API running:
```bash
python3 scripts/release_gate.py
```
Expected v0.17 reference result:

**RELEASE GATE: PASS — 240/240 checks across 9 suites**

## Optional: enable frontier-model intelligence
Arbiter does not require an LLM to resolve contracts. The model layer is advisory and can be disabled entirely.

Preferred OpenAI configuration:
```bash
export OPENAI_API_KEY='YOUR_KEY'
export ARBITER_MODEL_PROVIDER='openai'
export ARBITER_MODEL_DEFAULT='gpt-5.6-sol'
export ARBITER_MODEL_FAST='gpt-5.6-terra'
```
Then restart Arbiter.

Check model posture:
```bash
curl http://localhost:8000/api/model-gateway | python3 -m json.tool
```

## Production-shaped data plane
Do **not** point a live settlement deployment at the local SQLite database. A production-shaped environment should configure:

```bash
export ARBITER_ENV=production
export ARBITER_DATABASE_BACKEND=postgresql
export ARBITER_DATABASE_URL='postgresql://...'
export ARBITER_DATABASE_SSLMODE=require

export ARBITER_OBJECT_STORE_BACKEND=s3
export ARBITER_S3_BUCKET='...'
export ARBITER_S3_PREFIX='arbiter'
```

Install backend dependencies with:
```bash
python3 -m pip install -r backend/requirements-production.txt
```

If migrating pre-v0.17 PostgreSQL rows, assign tenant ownership explicitly before enabling RLS. For a verified single-tenant migration only:
```bash
export ARBITER_MIGRATION_DEFAULT_TENANT='tenant_...'
```

Check data-plane posture:
```bash
curl http://localhost:8000/api/data-plane | python3 -m json.tool
```

## Useful endpoints
```text
GET  /api/health
GET  /api/readiness
GET  /api/security-posture
GET  /api/developer
GET  /api/data-plane
POST /api/data-plane/self-test
POST /api/data-plane/backup
POST /api/data-plane/backup/verify

POST /api/semantic-analyze
POST /api/compile
POST /api/compile-and-create
POST /api/analyze
GET  /api/cases
GET  /api/cases/{case_id}

GET  /api/evidence-monitors
GET  /api/source-health
GET  /api/evidence-exceptions
GET  /api/resolution-reevaluations

GET  /api/approvals
GET  /api/settlement-packets
GET  /api/audit

GET  /api/model-gateway
GET  /api/model-invocations
POST /api/model-gateway/self-test
POST /api/ai/semantic-review
POST /api/cases/{case_id}/copilot
```

## Core boundary
> **AI interprets. Policy governs. Evidence proves. Deterministic logic resolves. Humans handle exceptions.**

A missing model API key does not disable Arbiter's binding control plane.

## Production status
v0.17 is **not production settlement certified**. The application-side production data plane is now implemented, but the managed cloud resources, identity/key custody, resilience, external observability, recovery drills, security assurance, and untouched holdout still need to be completed and evidenced. See `ENTERPRISE_READINESS.md`.

## Enterprise validation (v0.26)

Run all backend gates:

```bash
python3 scripts/release_gate.py
```

Expected: `RELEASE GATE: PASS — 419/419 checks across 17 suites`.

Static deployment preflight:

```bash
python3 scripts/deployment_preflight.py
```

For an AWS staging deployment, start with `deploy/aws/README.md` and run `terraform init`, `terraform fmt -check`, `terraform validate`, then `terraform plan` before any apply.

## v0.27 real-contract benchmark

The real holdout is intentionally not populated by the release package. When ready to collect it:

```bash
python3 scripts/collect_holdout_candidates.py --venue kalshi --venue polymarket --limit-per-venue 100 --out benchmarks/candidates_v0_1.jsonl
python3 scripts/freeze_holdout.py benchmarks/candidates_v0_1.jsonl --target 75 --out benchmarks/arb_gold_holdout_v0_1
python3 scripts/verify_holdout.py benchmarks/arb_gold_holdout_v0_1
python3 scripts/run_holdout.py benchmarks/arb_gold_holdout_v0_1
```

After the blind run is pinned, generate a report with `scripts/generate_benchmark_report.py`. See `REAL_WORLD_BENCHMARK.md` for the no-tuning and label-separation rules.
