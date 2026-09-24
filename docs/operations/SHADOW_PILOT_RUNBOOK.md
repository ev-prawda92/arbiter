# Arbiter Shadow Pilot Runbook — v0.25+

## Objective
Evaluate 50–100 historical or live contracts without altering the venue's official resolution or settlement.

## Workflow
1. Create a shadow pilot for the venue.
2. Import original contract title/rules and immutable venue contract ID.
3. Freeze the input text and provenance before Arbiter evaluation.
4. Run semantic analysis and compiler status (READY/REVIEW/BLOCK).
5. For live contracts, observe approved evidence in parallel with venue operations.
6. After the venue resolves, record the venue outcome and Arbiter shadow outcome.
7. Measure ambiguity detection, READY/REVIEW/BLOCK distribution, evidence completeness, operator time, agreement/disagreement, false holds, and false auto-resolve candidates.
8. Review disagreements individually; never collapse them into a marketing accuracy claim without adjudicated labels.

## Boundary
Shadow mode has zero settlement authority and cannot mutate the venue's official state.
