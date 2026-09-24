# Arbiter v0.11 — Active Evidence Infrastructure

v0.11 turns governed evidence from a manually submitted artifact into an actively monitored control-plane resource while keeping settlement authorization separate and fail-closed.

## Added
- Durable evidence monitor registry tied to approved contract authorities.
- Static fixture and opt-in HTTPS JSON adapters.
- Scheduled due-poll API plus supervised worker process (`scripts/evidence_worker.py`).
- Append-only evidence revisions with provenance hashes and parser/source metadata.
- Idempotent duplicate observation handling.
- Cross-authority conflict detection.
- Source outage state, exponential retry/backoff, and source-health summary.
- Durable resolution reevaluation requests when governed evidence changes.
- Evidence exceptions surfaced automatically in the operator Work Queue.
- Audit events for monitor lifecycle, evidence ingestion, exceptions, poll failures, and reevaluation requests.
- `scripts/evidence_gate.py` regression gate.

## Settlement boundary
v0.11 does **not** authorize settlement. Evidence changes request deterministic reevaluation; conflicts and outages create governed exceptions. Binding approval/settlement remains a later control layer.

## Validation target
Run the v0.9.5 coherence gate, v0.10 enterprise gate, and v0.11 evidence gate before tagging this release.
