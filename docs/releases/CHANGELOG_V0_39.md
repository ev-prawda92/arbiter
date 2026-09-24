# Arbiter v0.39: Precedent Engine

Every governed decision now becomes precedent. When new contracts arrive,
Arbiter checks them against the precedent record and shows which earlier ruling
applies and why. Departing from an applicable ruling requires a stated
distinction or an explicit overrule.

## What's new

**Precedents from decisions** (`backend/app/precedents.py`)
- Each decision record becomes a precedent holding the ruling, the decided
  contracts, and the clauses in those contracts that the ruling resolves.
- Superseding a decision retires its precedent.

**Arrival check** (venue intake)
- Every synced contract is matched against live precedent in three tiers:
  same clause, same template, related.
- Each match reports its evidence: both similarity scores, the closest decided
  contract, and the clause pair.
- Applicable matches are recorded in `precedent_matches` and in the audit chain.
- The work item names the ruling that applies.
- A market the classifier passes over, but that contains a clause a human has
  already ruled on, is brought in anyway. The cap is 50 per venue per scan.
  Re-triage never closes such work items.

**Consistency on every decision**
- `POST /api/decisions` checks the selection against applicable precedent and
  returns one of: novel, follows, consistent or divergent.
- A divergent decision is refused (409) unless it carries a `distinguish`
  reason or `overrules` a precedent.
- Overruling is prospective. The overruled decisions keep governing their own
  cases, but the whole line holding that ruling stops guiding new contracts.
- Split precedent (a ruling and a later distinction) is surfaced as a conflict.
- `POST /api/decisions/consistency` previews the check before anything is recorded.

**Appeal checks**
- `POST /api/appeals/check` names the decision that governs a contract and any
  applicable precedent.
- It returns a verdict (no ruling, matches ruling, contradicts ruling) and the
  options: uphold, distinguish or overrule. Each check is audited.

**Ask Arbiter** (`POST /api/ask`)
- Answers questions from the precedent record only, with citations.
- Retrieval is deterministic: coverage over IDF-weighted terms plus a small,
  declared lexicon of resolution vocabulary (die/death, acting/interim,
  leave/vacate).
- When nothing covers a question, it says so. No model generates answers.

**Workbench**
- New precedent panel: tier badge, the ruling, the clause ruled on beside the
  clause in this contract, and **Follow this ruling**.
- Live consistency status while the ruling is typed, with distinguish and
  overrule controls when the ruling departs from precedent.
- Ask Arbiter bar at the top.

**API**
- `GET /api/precedents`
- `GET /api/precedents/{id}`
- `GET /api/precedents/match/{contract_id}`

## Measured

On 838 real Kalshi/Polymarket markets from the recorded Sep 23–24 scans, the
same-template tier reaches the matching template in another event for **79.6%**
of markets (391/491), at **100% precision**. The 5 above-threshold matches with
no family label were reviewed: all are the same template under another ticker.
Exactly two cross-event clause links exist in the data, and both were reviewed as
correct. Method, full threshold table and limits:
[docs/benchmark/PRECEDENT_MATCHING.md](../benchmark/PRECEDENT_MATCHING.md).

## Validation

- **New `scripts/precedent_gate.py`: 49 checks.** They cover:
  - the measured thresholds
  - the reviewed pairs and links
  - a next G7 event matching on arrival
  - no stray matches across the rest of the scan
  - refuse, distinguish, follow and overrule
  - appeals, Ask Arbiter and supersession
  - fine-print exclusion and re-triage safety
  - audit-chain integrity
  - no change to contracts, evidence or resolutions
  - read endpoints that write nothing
  - an overrule that retires a line longer than five precedents
- 5 new unit tests.
- All earlier gates pass unchanged; release gate 452/452.

## Independent review

A separate reviewer, who had not seen the work, read the change before release.
It found seven defects, all fixed in this release:
- **Overrule stopped at the top five peers.** It now retires every precedent that
  holds the overruled ruling (gate P17).
- **Matching was slow.** The reviewer measured about 130 ms per contract on a
  synthetic set of 300 precedents with about 10 clauses each. Vectors are now cached
  by text, matches are reused at arrival, and a bigram prefilter skips clause pairs
  with no shared word pairs. The filter was checked against every clause pair in the
  838-market scans: it drops only name-only fragments. Matching now takes 13 ms per
  contract against 300 precedents built from real scan markets (up to 10 clauses
  each, 5.6 on average).
- **The precedent record was rebuilt on every request, from the newest 500
  decisions only.** It now covers every decision, runs only when decisions change,
  and runs only on write paths and at startup.
- **Read endpoints wrote to the audit chain.** They no longer write (gate P16).
- **Appeal checks recorded a caller-supplied actor.** They now record the
  authenticated principal.
- **A concurrent overrule could fail after the decision was recorded.** It is now
  a no-op.
- **Departing from a second, different holding while overruling one** now requires
  a stated distinction.

Also:
- The vector cache is keyed by contract text, so a rules change never reuses a
  stale vector.
- Retired precedents drop their derived matches.
- Re-triage revisits work routed by a precedent that is no longer live.

## Also

- `frontend/package-lock.json` now carries the product version, and the
  consistency test checks it.
- Venue intake records `review_class` on each work item's metadata.
