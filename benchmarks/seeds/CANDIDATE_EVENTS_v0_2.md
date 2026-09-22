# ARB-GOLD-PILOT-v0.2 — Candidate events dossier

Status: research notes, not a ready seed file. Every case below is a real,
documented event verified from public reporting. What is NOT yet verified for
any of them: (a) the market-level identifier that resolves through each venue's
API, and (b) whether both venues listed the same question and how each settled.
Those two steps need a live session against the venues and are the curator's
confirmation the benchmark rests on.

Per-case fields:
- class: the v0.2 hardness class it fills (see HARD_CORPUS_V0_2.md)
- polymarket: event URL confirmed from public search (event-level, still needs
  resolving to the settled market id/slug the Gamma /markets endpoint returns)
- kalshi: UNCONFIRMED unless noted — needs a lookup on Kalshi's side
- cross_venue: whether this is a genuine two-venue case or a within-venue dispute

---

## 1. Zelenskyy "suit" market
- class: disputed + interpretive_criteria
- what happened: A Polymarket market on whether Zelenskyy would "wear a suit
  before July" resolved NO despite his widely-noted NATO-summit jacket. ~$160–240M
  notional; a major UMA oracle dispute over what counts as a "suit."
- polymarket: https://polymarket.com/event/will-zelenskyy-wear-a-suit-before-july
- kalshi: UNCONFIRMED — check whether Kalshi ran an equivalent attire market.
- cross_venue: PROBABLY NO — this is a within-venue (UMA) dispute. Highest value
  as a `disputed`/`interpretive` case, not a cross-venue disagreement.
- why it matters: the cleanest public example of resolution hinging on an
  undefined qualitative term. Exactly the case a resolution layer must handle.
- sources: Decrypt, Forbes, CoinDesk (2025-07-07 reporting)

## 2. US–Iran nuclear deal (2025 windows)
- class: interpretive_criteria (what counts as a "deal"; timing windows)
- polymarket events (multiple, dated windows — pick the resolved one):
  - https://polymarket.com/event/us-x-iran-nuclear-deal-in-2025
  - https://polymarket.com/event/us-iran-nuclear-deal-by-june-30
  - https://polymarket.com/event/us-iran-nuclear-deal-before-august
- kalshi: UNCONFIRMED — Kalshi commonly lists geopolitical "deal/agreement" markets;
  check for a matching window.
- cross_venue: POSSIBLE — if both listed a dated "deal" market, near-certain
  interpretive disagreement given how differently venues define "deal."
- note: only seed a window that has actually RESOLVED; several of these may still
  be open, which disqualifies them from a resolved-contract holdout.

## 3. Venezuela 2024 presidential election
- class: revised_source + disputed
- what happened: Outcome contested; official result vs widely-reported tallies
  diverged, and resolution depended on which source a contract named.
- polymarket: CHECK — event under venezuela-presidential-election-2024 (verify slug)
- kalshi: UNCONFIRMED
- cross_venue: POSSIBLE
- sources: to attach at curation.

---

## Clean agreement / control candidates (fill `control_easy` + timing)

These are the unambiguous, both-likely-listed macro prints — good agreement
controls and source-precedence tests, low dispute risk:

- CPI month-over-month, a specific past release (BLS print; revision-prone → also
  tests `revised_source`).
- FOMC rate decision, a specific past meeting (clean source, timing-sensitive).
- Bitcoin above a round threshold on a named date (tests which price feed /
  timestamp each venue used → source precedence).

Kalshi tickers and Polymarket market ids for all of the above are UNCONFIRMED and
must be pulled from the live listings.

---

## What still has to happen (and needs live venue access)
1. Resolve each Polymarket event above to the specific SETTLED market
   (id or market-slug the Gamma /markets endpoint returns), and confirm it resolved.
2. Find the Kalshi ticker for the same question, and confirm its settled result.
3. Confirm the two markets ask the SAME question (the curator judgment).
4. Only then write a seed row and run collect_targeted_candidates.py.

Honest expectation from this dossier: cases 1–3 are strong `disputed`/`interpretive`
material even if they turn out to be single-venue. A confirmed CROSS-VENUE
disagreement still has to be found by checking both listings for the same
question — none is confirmed yet.
