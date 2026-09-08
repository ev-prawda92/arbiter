# Arbiter v0.21 — Settlement Assurance Harness

Adds an executable assurance layer without overstating internal validation as external certification.

- adversarial contract suite with hash-pinned results
- frozen holdout dataset registry
- immutable dataset hashes and evaluation hashes
- explicit certification requirements and blockers
- external security review and penetration test remain required
- production load, restore, failover, and incident exercises remain required
- assurance activity written to the audit chain
- automated settlement-assurance release gate

v0.21 explicitly reports `production_settlement_certified: false`. It is an assurance-readiness milestone, not independent certification.
