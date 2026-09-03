# Arbiter v0.8 — Operational Workflow

## Product shift

v0.8 turns Arbiter from a set of resolution-control capabilities into an operator-facing workflow system with an executive readout.

The operating model is now:

**Arbiter watches → advisory agent triages → compliance / resolution ops handles exceptions → executives consume outcomes.**

## Executive Overview

Added a read-only executive landing view focused on the questions leadership actually needs answered:

- overall resolution posture
- resolution-risk notional
- held notional before payout
- active operator exceptions
- primary portfolio risk driver
- audit-chain integrity
- highest-risk contracts

The executive view is intentionally low-click and outcome-oriented.

## Compliance / Resolution Operations Work Queue

Added a derived operational queue that prioritizes human work from governed Arbiter state, including:

- resolution HOLDs
- monitored contracts
- authority status issues
- evidence-ledger gaps
- audit-integrity failures

Work items have stable IDs, severity, recommended action, owner role, represented notional, and persisted operator state (`open`, `in_progress`, `resolved`). Status changes are audit logged.

## Resolution Operations Agent v0.1

Added the first advisory agent layer. In v0.8 it is deterministic/model-free so every statement is traceable to Arbiter state. It produces:

- a concise daily headline
- portfolio exposure summary
- held-payout summary
- primary risk driver
- audit integrity status
- prioritized top actions

The agent is explicitly non-binding and cannot alter contract terms, evidence, policy, resolution outcomes, or payout authorization.

Operator dispositions are persisted as a future learning/evaluation signal.

## API

New endpoints:

- `GET /api/overview`
- `GET /api/work-queue`
- `POST /api/work-queue/{work_item_id}`
- `GET /api/agent/brief`

## Persistence

Added `work_item_state` to the local reference database. It stores operator status, owner, note, timestamp, and actor. Work items themselves remain derived from governed Arbiter state rather than becoming a second source of truth.

## Validation

- Python modules compile successfully.
- v0.5 development benchmark remains unchanged: 90/90 valid cases, 70/70 controlled defects detected, clean false-positive rate 0.0 in the calibration suite.
- New Overview, Work Queue, Agent Brief, Executive, Health, and Infrastructure API smoke tests return HTTP 200.
- Work-item state transitions were tested and audit logged.

The frontend dependency install/build timed out in the build environment, so a completed Vite production build is not claimed here. Run `npm install && npm run build` locally after syncing the release.
