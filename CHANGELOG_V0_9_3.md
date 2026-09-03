# Arbiter v0.9.3 — Review Semantics

## Coherent READY / REVIEW / BLOCK states

- Added explicit handling for repairable incompleteness versus hard blocking defects.
- Contracts with a coherent authority, objective event, and settlement window can now enter `REVIEW` when exact cutoff details remain missing.
- `BLOCK` remains reserved for hard inconsistencies or missing binding concepts such as title/rules mismatch, no usable authority, conflicting source precedence, or no objective condition.

## Compiler improvements

- Compiler version `0.1.2`.
- Recognizes event-style Federal Reserve rate-cut conditions as `rate_change_event`.
- Recognizes windows such as `by the end of September 2026` as a valid settlement window.
- Missing time-of-day and timezone remain explicit unresolved fields and therefore require governed review rather than being fabricated.
- Added deterministic recommended drafting fixes for unresolved fields.

## Resolution gate

- `READY` may proceed to the normal evidence/resolution path.
- `REVIEW` remains HELD pending governed human review or specification repair.
- `BLOCK` remains a hard HOLD with resolution and payout authorization disabled.
