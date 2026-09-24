# Production Reliability Model

Arbiter's settlement path must tolerate retries, duplicate delivery, process crashes, source outages, and downstream failures without silently duplicating or losing authoritative actions.

## Durable jobs
Jobs are persisted before execution. Workers claim a time-bound lease. Completion is restricted to the lease owner. Failed jobs either return to the queue or move to a dead-letter state when the maximum attempt count is reached.

## Idempotency
External operations can be pinned to an idempotency key and request hash. Repeating the same operation returns the stored result. Reusing a key with a different request is rejected.

## Signed webhooks
Outbound event envelopes carry a timestamp, nonce, canonical payload hash, and signature. Verification enforces signature integrity, clock tolerance, and single-use nonce replay protection.

## Production boundary
The current implementation is a local reference implementation backed by Arbiter's durable store. A settlement-critical deployment still requires managed PostgreSQL, a managed durable queue or equivalent, multi-instance lease/concurrency validation, HA, backups and restore exercises, KMS/HSM key custody, external metrics/logging/tracing, alerting, load testing, chaos/failure testing, and independent security review.
