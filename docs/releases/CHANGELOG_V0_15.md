# Arbiter v0.15 — Production Reliability Foundation

## Added
- Durable job queue with worker leases, retry scheduling, max-attempt handling, and dead-letter state.
- Persistent operation idempotency store with request-hash mismatch protection.
- Signed webhook envelopes with timestamp, nonce, payload hash, HMAC signature, and replay detection.
- Reliability schema migration registry.
- Reliability operational posture endpoint and job registry APIs.
- Production configuration gate for webhook signing key custody.
- `scripts/reliability_gate.py` and integration into the one-command release gate.

## Boundary
v0.15 implements application-level reliability contracts and local durable reference storage. It does **not** claim managed PostgreSQL, managed queue infrastructure, HA, KMS/HSM signing, external observability, penetration testing, or production settlement certification are complete.
