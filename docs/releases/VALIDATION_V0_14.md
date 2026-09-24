# Arbiter v0.14 Validation

The v0.14 identity/tenant gate verifies:
- API version and health
- local principal identity context
- tenant context
- principal type
- identity posture
- tenant registry
- local tenant seed
- governed tenant creation
- duplicate-tenant rejection
- service-principal registration
- tenant-filtered principal listing
- rejection of unknown tenant binding
- rejection of invalid principal type
- audit logging
- readiness after identity operations

Run the full stack with:

```bash
python3 scripts/release_gate.py
```
