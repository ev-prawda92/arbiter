# Arbiter v0.12 — Approval & Settlement Control

## Added

- Maker-checker approval requests for resolution-run settlement authorization.
- Independent approval decisions with one-vote-per-actor enforcement.
- Fail-closed rejection of HELD/PENDING/REVIEW/BLOCK runs from settlement approval.
- Signed `arbiter.settlement-authorization.v1` packets with pinned run, contract, policy, engine, evidence, and approval metadata.
- Idempotent packetization: one authorization packet per approved request.
- Exchange-profile terminal actions:
  - `kalshi_dcm` → exchange resolution authorization handoff.
  - `polymarket_uma` → oracle proposal/dispute packet handoff.
- Production configuration gate for settlement signing secret.
- Governed policy workflow: Draft → Submit → Independent Approval → Activate.
- Production disables direct active-policy mutation.
- New API scopes: `approvals:write`, `settlement:authorize`.
- New APIs: `/api/approvals`, `/api/settlement-packets`, `/api/policy/drafts` and governed policy actions.
- Policy UI upgraded from read-only display to governed draft/approval/activation workflow.
- `scripts/settlement_gate.py` automated regression harness.

## Boundary

v0.12 does **not** execute a payout, exchange settlement, or UMA/oracle transaction. It creates a governed, signed authorization artifact for a downstream terminal adapter. Production cryptographic signing still needs to move to KMS/HSM-backed asymmetric keys before live settlement.
