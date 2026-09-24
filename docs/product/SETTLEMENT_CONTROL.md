# Settlement Control Boundary

Arbiter v0.12 separates **resolution** from **authorization** from **execution**.

1. A governed resolution run completes.
2. HELD/PENDING/REVIEW/BLOCK outcomes are ineligible for authorization.
3. A maker requests settlement handoff authorization.
4. An independent checker approves or rejects; the maker cannot approve their own request.
5. Arbiter creates a signed, version-pinned authorization packet.
6. A venue-specific downstream adapter may consume that packet.

Arbiter v0.12 stops at step 5. It does not send a payout instruction, settle an exchange contract, or submit an oracle transaction.

## Packet pins

- resolution run ID/hash
- contract ID/version
- policy version
- engine version
- evidence IDs
- approved decision actors/timestamps
- exchange profile
- terminal action
- payload hash and signing metadata

## Production signing

Local development uses a clearly marked non-production HMAC mode. Production mode fails readiness if `ARBITER_SETTLEMENT_SIGNING_SECRET` is absent. Before live settlement, replace shared-secret HMAC with KMS/HSM-backed asymmetric signing, key rotation, verifier distribution, and revocation procedures.
