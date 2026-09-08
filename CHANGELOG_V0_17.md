# Arbiter v0.17 — Production Data Plane

## Added
- `backend/app/production_data.py` as the single durable-data infrastructure boundary.
- Dual database support: SQLite for local/reference development and PostgreSQL for production deployments.
- Lazy psycopg 3 PostgreSQL adapter preserving Arbiter's existing store API.
- Request/worker-scoped tenant, principal, and request context propagated into PostgreSQL sessions.
- PostgreSQL row-level-security migration machinery with `ENABLE ROW LEVEL SECURITY`, `FORCE ROW LEVEL SECURITY`, and `WITH CHECK` tenant policies.
- Fail-closed migration behavior for pre-v0.17 rows without explicit tenant ownership.
- Content-addressed immutable object storage for raw evidence payloads.
- Local object-store reference adapter and managed S3 adapter with server-side encryption support.
- Active Evidence now preserves the canonical raw payload object reference in each governed evidence record.
- PostgreSQL transaction-scoped advisory-lock serialization for concurrency-sensitive settlement packet creation.
- Local process serialization fallback for SQLite development.
- SQLite online backup + SHA-256 manifest + `PRAGMA integrity_check` restore-verification path.
- Production PostgreSQL backup/PITR recovery posture and restore-drill requirements.
- `/api/data-plane`, `/api/data-plane/self-test`, `/api/data-plane/backup`, and `/api/data-plane/backup/verify`.
- `scripts/data_plane_gate.py` with 28 deterministic checks.
- Full release gate expanded to 240/240 checks across 9 suites.

## Production configuration gates
Production now fails closed unless:
- `ARBITER_DATABASE_BACKEND=postgresql`;
- `ARBITER_DATABASE_URL` is configured;
- psycopg 3 is installed;
- PostgreSQL TLS is required;
- `ARBITER_OBJECT_STORE_BACKEND=s3`;
- an S3 bucket is configured;
- boto3 is installed;
- the pre-existing enterprise/security gates also pass.

## Tenant isolation
v0.17 introduces database-enforced tenant policies for the core contract, authority, evidence, resolution, audit, workflow, approval, policy, reliability, and model-invocation tables. PostgreSQL sessions receive tenant context from the authenticated Arbiter principal. Missing tenant context cannot satisfy the RLS `WITH CHECK` policy.

Existing pre-v0.17 production rows are **not silently assigned** to a tenant. A migration must explicitly set `ARBITER_MIGRATION_DEFAULT_TENANT` or perform a venue-specific ownership migration before RLS is activated.

## Evidence durability
Raw evidence observations are now stored separately from normalized evidence records using content-addressed SHA-256 object keys. The governed evidence record continues to carry the canonical payload hash and now also retains the immutable object reference in metadata.

## Model default correction
The OpenAI default model identifier is `gpt-6-astra`, with `gpt-5.6-terra` as the fast/cost-balanced tier. Environment overrides remain supported.

## Not included / not claimed
v0.17 is **not production settlement certified**. It implements the application-side production data-plane boundary, but live certification still requires actual managed PostgreSQL/S3 deployment, connection/runtime tuning, externally observed backups and PITR, deployment-level HA/failover, SSO/key custody, observability, load/chaos testing, security review, penetration testing, and untouched real-contract validation.
