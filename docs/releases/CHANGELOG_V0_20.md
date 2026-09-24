# Arbiter v0.20 — Production Operations & Resilience

Adds operational controls needed to run Arbiter as long-lived infrastructure:

- dependency/readiness telemetry
- bounded-load admission and rate-limit posture
- worker backlog/backpressure states
- governed incident lifecycle with audit logging
- deterministic recovery-drill records and hashes
- audit replay, database-read, queue-recovery, and backup-posture drills
- operations posture API
- explicit requirement for external production observability/APM
- automated operations/resilience release gate

This release provides application-level resilience controls; actual multi-zone HA, external alerting, managed failover, and infrastructure chaos tests still require a deployed production environment.
