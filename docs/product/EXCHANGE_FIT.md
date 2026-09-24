# Arbiter Exchange Fit: Kalshi and Polymarket

## Shared control problem
Both operating models require precise market rules, explicit resolution sources, timing semantics, edge-case handling, evidence provenance, and a defensible record of how a result was reached. Arbiter's shared core therefore remains: **Define → Evidence → Resolve → Audit**.

## Kalshi / DCM pattern
Arbiter fits as a resolution control plane around the exchange's governed market and settlement workflow: pre-listing contract checks, source hierarchy, evidence capture, deterministic controls, holds/review, approvals and audit. The exchange remains responsible for its rules, regulatory obligations and settlement process. Arbiter should be described as supporting those controls, not as conferring CFTC compliance.

## Polymarket / UMA optimistic-oracle pattern
Arbiter fits earlier and around the oracle boundary: rule compilation, resolution-source governance, evidence collection, proposal recommendation, challenge/dispute evidence packets, ambiguity detection and audit. Arbiter must not claim to replace UMA finality for markets whose rules specify the UMA resolution mechanism.

## Product implication
The core domain model should remain venue-neutral. The final action is adapter-specific:
- DCM adapter: governed resolution/settlement authorization handoff.
- Optimistic-oracle adapter: proposal/dispute recommendation + evidence packet handoff.

This keeps one Arbiter control plane while respecting materially different settlement authorities.
