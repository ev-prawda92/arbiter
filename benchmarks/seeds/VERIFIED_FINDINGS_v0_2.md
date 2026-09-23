# ARB-GOLD-PILOT-v0.2 — Verified findings (live pull 2026-09-20)

Pulled directly from each venue's public API via browser. These are real,
collector-ready identifiers with confirmed resolution.

## Iran nuclear deal — CROSS-VENUE AGREEMENT (both NO)

Polymarket:
- market id: 521878
- slug: us-x-iran-nuclear-deal-in-2025
- question: "US-Iran nuclear deal in 2025?"
- resolved: NO  (outcomePrices Yes=0 / No=1), closed 2026-01-01
- host: gamma-api.polymarket.com

Kalshi (series KXUSAIRANAGREEMENT):
- KXUSAIRANAGREEMENT-27-26AUG "Will the US agree to a new Iranian nuclear deal before August?" (Before Aug 1 2026) -> result NO, finalized
- KXUSAIRANAGREEMENT-27-26SEP "Will the US agree to a new Iranian nuclear deal this year?" (Before Sep 1 2026) -> result NO, finalized
- host: api.elections.kalshi.com  (NOT external-api.kalshi.com)

Verdict: both venues resolved Iran-nuclear-deal markets to NO. This is an
AGREEMENT case, not a disagreement. Value: interpretive-agreement control, and
a source-precedence test (Kalshi publicly disclaimered that the June US-Iran MOU
"does not count" as a deal; whether Polymarket applied the same bar is a
curation question worth recording).

Note on windows: Polymarket used calendar-2025; Kalshi's series starts 2026
(no -25 event). Same topic, different windows -- a reminder that cross-venue
pairing must match the window, not just the subject.

## COLLECTOR BUG FOUND (now patched)

Kalshi serves election / geopolitics / political markets ONLY on
api.elections.kalshi.com. The collector previously queried only
external-api.kalshi.com, which returns EMPTY for these series -- exactly the
categories the hard corpus depends on. Patched collect_kalshi and
fetch_kalshi_market to query both hosts (KALSHI_HOSTS).

## Standing conclusion

Even with live access, a genuine cross-venue DISAGREEMENT remains unconfirmed.
The marquee geopolitical case (Iran) resolved the same way (NO) on both venues.
This is the third independent signal that true disagreements are rare; the
corpus's disagreement class may end up small, and the spec's honest-limitation
clause (record the shortfall, do not backfill) applies.

## Zelenskyy "suit" — interpretive_criteria + disputed (VERIFIED)

Polymarket:
- market id: 546814
- slug: will-zelenskyy-wear-a-suit-before-july
- question: "Will Zelenskyy wear a suit before July?"
- resolved: NO (Yes=0 / No=1), closed 2025-07-09
- criteria (verbatim): resolves YES if Zelenskyy is "photographed or videotaped
  wearing a suit between May 22 and June 30, 2025 ET ... resolution source will
  be a consensus of credible reporting." No operational definition of "suit."
- dispute signal (from API): umaResolutionStatuses = proposed/disputed x5 --
  FIVE dispute rounds before final resolution.
- host: gamma-api.polymarket.com

Why it is a gold case: the qualitative term ("suit") is undefined and the source
is "consensus of credible reporting" -- exactly the failure mode a resolution
layer must handle. The five UMA dispute rounds are objective evidence of the
`disputed` class, not a judgment call. Kalshi equivalence not required for this
class; single-venue is fine.

## Venezuela 2024 presidential election — multi_source_conflict + disputed (VERIFIED)

Polymarket (event venezuela-election-winner), resolved 2024-08-06:
- id 502006 "Will Edmundo Gonzalez win the 2024 Venezuela presidential election?" -> YES
- id 502002 "Will Nicolas Maduro win...?" -> NO
- (others 502003/502004/502005 -> NO)
- host: gamma-api.polymarket.com

Why it is a gold case: Venezuela's official electoral authority (CNE) declared
MADURO the winner. Polymarket resolved GONZALEZ. The named-official source and
the market resolution diverge -- the exact multi_source_conflict the corpus
needs. Curation note: pull the market's resolution-source rules text to confirm
which source it named, and record the CNE-vs-resolution divergence as the case.

## CPI March 2025 (monthly) — revised_source / control (VERIFIED)

Polymarket (event march-inflation-monthly), resolved 2025-04-10:
- id 527838 "monthly inflation increase by 0.1% or less in March?" -> YES
- id 527839 (0.2%) -> NO ; 527840 (0.3%) -> NO ; 527841 (0.4%) -> NO ; 527842 (0.5%+) -> NO
- host: gamma-api.polymarket.com

Why: clean multi-bucket macro print, revision-prone (BLS revises CPI). Good
revised_source case and a legibility control. Kalshi lists CPI too (series to
confirm) -> potential genuine dual-listing on an unambiguous number.
