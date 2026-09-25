# Arbiter v0.43: Precise Live Triage

The first full-book scan of Kalshi (Sep 24 2026: 38,076 open markets in Politics,
Elections, Economics, Financials, and Climate and Weather) exposed two defects in live
triage. v0.43 fixes both. The benchmark classifier is unchanged; only the live-intake
layer that decides what reaches a human changed.

## What was wrong

- **Noise.** v0.39 triage flagged 20,953 of 38,076 markets (55%). 19,627 of those were
  election markets flagged as "multi-source conflict" only because they were elections
  that named an official source. Rules like "certified/official results only, not
  preliminary results" are the fix for a source question, not the problem.
- **Scale dependence.** Triage learned "template" wording from whatever pool it was
  scanning, so a market's flag depended on its neighbours. The seven G7 leader-out
  markets were flagged in a 200-market scan and passed in the 38,076-market scan with
  identical rules text.

## What changed

- **Source conflict needs two sources and no tie-break.** An election market is flagged
  only when its rules admit a second source for the same fact ("an overwhelming
  consensus of credible reporting may also be used", "or credible sources") and never
  say which one wins. A rule that routes ambiguity "solely" to the official body, or
  lets media calls be used "only as those provisions allow", is not a conflict.
- **A dispute needs a dispute.** A standing exclusion written into the rules ("does not
  count") is precision. A market is flagged as disputed only when it has recorded
  dispute rounds or the venue appended a clarification after listing
  ("Clarification (09/03/26): ...").
- **Triage reads each market's own text.** Nothing is learned from the scan pool. The
  only wording triage discounts is a fixed, versioned floor: Polymarket's standard
  "consensus of credible reporting" template, and Kalshi's election Accelerated
  Resolution provision (defined once in Kalshi's contract terms). The same market gets
  the same answer alone or in a 38,000-market scan. Learned templates are still
  computed and still used for precedent matching, where they only affect which past
  ruling is suggested.
- **Flags are reported by drafting family.** Discovery now reports flagged markets by
  Kalshi series (Polymarket event) and by reason. One rules template means one fix,
  so `sync_venues.py` prints the 15 largest families.

## Measured on the Sep 24 full-book scan

Every one of the 20,953 markets v0.39 flagged was re-triaged under v0.43, using the
rules text captured in the review database:

| | v0.39 | v0.43 |
|---|---|---|
| Flagged | 20,953 | 1,151 |
| Multi-source conflict | 19,627 | 0 |
| Revision-prone release not pinned | 884 | 894 |
| Disputed (dated clarification) | 403 | 168 |
| Interpretive wording | 39 | 89 |
| Drafting families | 2,823 events | 92 series |

The rest of the book (17,123 markets v0.39 passed) was not re-measured here. v0.43
triage no longer discounts pool-learned wording, so some of those markets may now flag.
Rerun the full scan to measure it.

## Gates

- `venue_intake_gate` V18 (new) covers 81 real markets sampled from the full-book scan,
  with their rules text verbatim (`tests/fixtures/kalshi_triage_2026-09-24.json.gz`).
  It checks that:
  - each triages as reviewed;
  - no election market that names its certifying authority is a source conflict;
  - the Xi-succession, G7 and CPI wording is flagged;
  - dated clarifications stay flagged;
  - every market's flag is identical alone and inside a 580-market pool.
- V13, V15, V16, V17 expectations are updated to v0.43 triage, with each dropped flag
  explained in the gate.
- `precedent_gate` and `audit_trail_gate` setups are updated for the smaller Sep 24
  queue (22 work items, down from 25).
