# Arbiter database migrations

v0.17 introduces the production PostgreSQL data-plane migration boundary.

- `postgresql/001_v0_17_tenant_rls.sql` is the auditable reference SQL for tenant columns and row-level security.
- Runtime application startup uses `backend/app/production_data.py` so it can inspect pre-existing rows and **fail closed** instead of silently assigning unknown rows to a tenant.
- For a pre-v0.17 production database, rehearse the migration against a restored snapshot first. Assign tenant ownership from authoritative customer/venue data, then enable `NOT NULL` + FORCE RLS.
- Never use `ARBITER_MIGRATION_DEFAULT_TENANT` for a multi-tenant database. It exists only for a verified single-tenant migration.

Production migration evidence should include schema checksum, before/after row counts, tenant-ownership reconciliation, rollback plan, and a two-tenant isolation test.
