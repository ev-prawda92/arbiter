# Arbiter v0.17 Validation

## Production data-plane gate
Run against a live local Arbiter instance:

```bash
python3 scripts/data_plane_gate.py --base-url http://127.0.0.1:8000
```

Expected:

**28/28 PASS**

The suite validates:
- v0.17 API version and data-plane posture;
- explicit PostgreSQL production requirement;
- transaction/advisory-lock posture;
- PostgreSQL tenant RLS + FORCE RLS + `WITH CHECK` policy shape;
- the tenant-scoped table registry;
- content-addressed SHA-256 object storage;
- deterministic object round-trip verification;
- qmark-to-psycopg SQL translation without corrupting quoted literals;
- request/worker tenant context switching and restoration;
- zero settlement authority for the data-plane self-test;
- SQLite online backup creation;
- SHA-256 backup manifest creation;
- SQLite integrity verification of the backup;
- infrastructure and developer-manifest integration.

## Complete release gate

```bash
python3 scripts/release_gate.py --base-url http://127.0.0.1:8000
```

Reference v0.17 build result:

**RELEASE GATE: PASS — 240/240 checks across 9 suites**

Suite totals:
- coherence: 48
- enterprise boundary: 14
- active evidence: 27
- settlement control: 30
- semantic contract: 29
- identity & tenant: 17
- production reliability: 27
- model intelligence: 20
- production data plane: 28

## Important limitation
The reference release gate runs against SQLite/local object storage so it is deterministic and does not require cloud credentials. It validates the PostgreSQL adapter/RLS policy machinery and production configuration gates, but **does not substitute for a real managed PostgreSQL + S3 deployment test**.

Before production certification, execute the same application tests against the deployed production-shaped environment and add:
- database migration rehearsal and rollback evidence;
- tenant-isolation tests using two real PostgreSQL tenants;
- concurrent settlement-packet tests across multiple app instances;
- backup/PITR restore drill into an isolated environment;
- object-store retention/encryption/access-policy validation;
- load, soak, failover, and chaos testing.
