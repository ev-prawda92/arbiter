# Arbiter v0.35 — Decisions Clear the Work They Answer

v0.34 recorded governed decisions but nothing consumed them: recording a
decision moved cases to `in_progress` and the queue stayed the same size.
v0.35 closes that loop. An authoritative decision now clears the work it
answers, and the decision workbench shows the result.

## What changed

- `decision_operations.apply_authoritative_decisions(queue, decisions)`:
  on every queue build, work answered by an authoritative (non-superseded)
  decision is marked resolved with `governed_by` provenance (decision id,
  hash, type, selection, cluster).
- `main._workflow_payload` applies it, so the work queue, operations
  intelligence, overview and the decision re-evaluation all see cleared work.
- Decision workbench keeps the outcome visible after the decided pattern
  clears ("One decision cleared N cases", before/after, cleared cases listed).

## Rules (enforced by `scripts/decision_clearing_gate.py`)

- **Derived, not stored.** Clearing is recomputed on every build. Superseding
  or withdrawing a decision re-derives it; dropped cases reopen.
- **Exact coverage.** Only the decision's recorded `affected_case_ids`, and
  only while each case still belongs to the decision's work pattern.
- **Judgment blockers only.** timing revision, policy interpretation,
  authority conflict, evidence conflict / review.
- **Never cleared by a decision:** payout HOLDs, suspended or monitored
  sources, audit-chain breaks, missing evidence.
- **Operators win.** A case reopened by an operator after the decision stays open.
- **Workflow only.** Contract terms, evidence, YES/NO/HOLD, settlement and
  payout are never changed.

## Validation

- New Decision Clearing gate (24 checks) in CI.
- All existing gates pass, including the full release gate (452/452).
