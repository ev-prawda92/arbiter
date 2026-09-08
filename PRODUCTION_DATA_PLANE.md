# Arbiter Production Data Plane — v0.17

## Purpose
The production data plane is the infrastructure boundary beneath Arbiter's semantic, evidence, resolution, approval, reliability, and model layers.

Local development remains intentionally simple:

```text
Arbiter → SQLite + local content-addressed object store
```

Production is fail-closed toward:

```text
Arbiter API / workers
        │
        ├── PostgreSQL
        │     ├── transactions
        │     ├── tenant session context
        │     ├── FORCE RLS
        │     └── advisory-lock serialization
        │
        └── managed object storage
              ├── SHA-256 content addressing
              ├── encryption at rest
              └── immutable raw evidence payloads
```

## Environment
A production-shaped deployment should configure at minimum:

```bash
export ARBITER_ENV=production
export ARBITER_DATABASE_BACKEND=postgresql
export ARBITER_DATABASE_URL='postgresql://...'
export ARBITER_DATABASE_SSLMODE=require

export ARBITER_OBJECT_STORE_BACKEND=s3
export ARBITER_S3_BUCKET='...'
export ARBITER_S3_PREFIX='arbiter'
# optional but preferred when a customer-managed key is required
export ARBITER_S3_KMS_KEY_ID='...'
```

The application also retains all existing production authentication, settlement-signing, webhook-signing, CORS, and identity requirements.

## Tenant context and RLS
The authenticated principal establishes the tenant context for the request. v0.17 binds that context to PostgreSQL using transaction-local settings:

```text
arbiter.tenant_id
arbiter.principal_id
arbiter.request_id
```

Tenant tables use both read and write enforcement:

```sql
USING (tenant_id = current_setting('arbiter.tenant_id', true))
WITH CHECK (tenant_id = current_setting('arbiter.tenant_id', true))
```

`FORCE ROW LEVEL SECURITY` is enabled so the application table owner cannot casually bypass the policy during ordinary runtime access.

## Migration safety
v0.17 intentionally refuses to guess tenant ownership for historical production rows. If a pre-v0.17 PostgreSQL database contains rows with no `tenant_id`, the RLS migration stops until ownership is explicitly assigned.

For a single-tenant migration only, an operator can set:

```bash
export ARBITER_MIGRATION_DEFAULT_TENANT='tenant_...'
```

Multi-tenant migrations should instead assign rows from authoritative venue/customer ownership data before enabling RLS.

## Evidence object storage
The normalized `EvidenceRecord` remains the settlement-facing governed record. Raw source payloads are preserved separately using canonical JSON bytes and a SHA-256 content address.

Example record metadata:

```json
{
  "raw_object": {
    "backend": "s3",
    "algorithm": "sha256",
    "digest": "...",
    "object_key": "arbiter/objects/sha256/ab/abcdef..."
  }
}
```

The object-store reference does **not** replace the evidence record hash, authoritative-source controls, or deterministic resolution logic.

## Concurrency
Settlement packet creation is serialized by approval ID. PostgreSQL uses `pg_advisory_xact_lock(hashtext(key))`; local SQLite uses an in-process lock. The database uniqueness constraints and existing idempotency controls remain a second line of defense.

## Backups and recovery
Local reference mode supports online SQLite backups with a SHA-256 manifest and integrity check.

Production PostgreSQL should use the managed database provider's:
- automated encrypted snapshots;
- point-in-time recovery;
- cross-zone durability;
- retention policy;
- isolated restore environment;
- application smoke/release-gate validation after restore.

Arbiter intentionally does not expose a production `pg_dump` of a live settlement database through the web API.

## Certification boundary
This module is application infrastructure, not certification evidence by itself. Production certification still requires proof from the deployed environment: IAM, network policy, encrypted storage, backup/PITR drills, HA/failover, observability, incident response, load/failure testing, and independent security assessment.
