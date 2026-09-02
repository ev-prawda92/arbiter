# Arbiter v0.7 — Executive Portfolio Intelligence

## Shared executive control plane

Added a read-only executive portfolio layer that presents the same governed resolution state through role-specific operating lenses:

- **Executive** — overall settlement-risk posture, resolution-risk notional, dominant risk driver, control integrity.
- **Compliance** — contracts held for review, coverage gaps, highest-priority control interventions.
- **Market Operations** — weak contract templates, drafting/remediation priorities, dominant ambiguity patterns.
- **Finance / CFO** — held pre-payout notional, monitored exposure, largest exposed contracts.

The lenses change prioritization and presentation only. They do not change settlement logic.

## API

- Added `GET /api/executive`.
- Refactored the existing portfolio payload into a reusable internal function.
- Executive intelligence combines portfolio analytics with v0.6 resolution-control state.

## UI

- Renamed the primary navigation item from **Intelligence** to **Portfolio**.
- Added an executive portfolio header with total notional, resolution-risk notional, held pre-payout notional, risk percentage, primary risk driver, and audit-chain status.
- Added role tabs for Executive, Compliance, Market Ops, and Finance / CFO.
- Preserved portfolio posture, risk-pressure, highest-risk contracts, category concentration, and coverage-gap views.

## Boundary

Executive Portfolio Intelligence is read-only. It cannot alter contract rules, evidence, policy, or resolution outcomes.
