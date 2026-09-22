# ARB-GOLD-PILOT-v0.2 — Hard Corpus Specification

Status: proposed
Supersedes nothing. v0.1 stays frozen and valid for what it measures.

## Why v0.2 exists

ARB-GOLD-HOLDOUT-v0.1 is methodologically sound and substantively easy.

Measured facts about v0.1 (75 cases, frozen 2026-09-09):

- Every case is a price-threshold contract. Polymarket rows are `"Ethereum above 2,520 on September 9, 2PM ET?"`. Kalshi rows are auto-generated cross-category strike bundles titled `"yes Target Price: $2.5997,yes Target Price: $1,271.8520"`.
- 57 of 75 cases have `resolution_source: null`.
- Kalshi `rules` text is a trademark disclaimer, not resolution criteria. It passes `--min-rules-chars 40` on length while carrying no criteria.
- `evidence.jsonl` is empty: 0 rows, `evidence_case_count: 0`, hash `e3b0c442...` (the empty-string SHA).
- All 75 cases are `category: "uncategorized"`.

Consequences:

1. The deterministic YES/NO resolution path has **zero** test coverage, because scoring it requires evidence and there is none.
2. A price threshold crossing a number is not a resolution problem. There is nothing to arbitrate, so a strong v0.1 score does not support any claim the product makes.
3. The corpus was selected by what the settled-markets endpoints return in bulk, not by what is hard. `collect_holdout_candidates.py` pages `status=settled` and crypto strike ladders dominate that page.

v0.2 exists to measure the product's actual claim: that Arbiter behaves correctly on contracts whose resolution is *contested, revised, late, or source-dependent*.

## Non-negotiables carried forward from v0.1

These are not relaxed for v0.2.

- Do not tune Arbiter against this corpus. Weaknesses are recorded, fixed against the development corpus, and re-measured on a future holdout version.
- `labels.jsonl` is physically separate and never opened by the blind runner.
- Missing evidence resolves to HOLD. Never a guessed YES/NO.
- A frozen dataset is never edited. Create v0.3.

## What changes

### 1. Selection targets hardness, not availability

Target: 100 cases. Sampled deliberately, not round-robin off an API page.

Quota by hardness class (the classes are the point of the corpus and become `category`):

| Class | Target | Definition |
|---|---|---|
| `interpretive_criteria` | 35 | Resolution hinges on a qualitative term the rules do not define operationally — "permanent", "official", "announced", "credible", "substantially". |
| `disputed` | 25 | Resolution was publicly contested: UMA dispute round, venue statement/clarification, documented trader dispute, or press coverage. |
| `revised_source` | 15 | The authoritative source published a value and later revised it (BLS/CPI revisions, election certification following a call, corrected sports statistics). |
| `multi_source_conflict` | 8 | Named resolution sources disagreed at resolution time. |
| `late_or_void` | 7 | Resolved materially after `closed_at`, voided, or extended. |
| `cross_venue_disagreement` | 5 | Same real-world event listed at both venues, resolved to different outcomes. OPPORTUNISTIC — keep every confirmed one, do not force the count. |
| `control_easy` | 5 | Price thresholds carried over from v0.1's population, retained as a floor: a system failing these has regressed. |

### Why these weights (revised 2026-09-20)

The original plan made `cross_venue_disagreement` the anchor class at 15. Three
independent checks say that class is rare and cannot carry that weight:

1. The fuzzy join over the 200-row v0.1 candidate pool found ZERO genuine
   cross-venue matches (the two venues weren't listing the same events).
2. The documented marquee cases (Zelenskyy suit, Iran MOU) turned out to be
   WITHIN-venue disputes over definition, not two venues disagreeing.
3. A live pull confirmed it directly: on the highest-profile dual-listed
   geopolitical question (US-Iran nuclear deal), both venues resolved NO. They
   agreed. See VERIFIED_FINDINGS_v0_2.md.

So the anchor moves to `interpretive_criteria` + `disputed` (60 of 100), which
the same evidence shows are plentiful: nearly every hard case is hard because a
qualitative term was undefined or a resolution was publicly contested, whether
or not a second venue existed. `cross_venue_disagreement` stays in the corpus as
a small opportunistic class — a confirmed one is still the most legible possible
case (two regulated venues, one event, two answers), so keep any that surface,
but do not spend curation effort manufacturing the count.

Rationale for `control_easy`: without it, a v0.2 score is not comparable to v0.1
and a regression could hide behind a harder corpus.

The honest-limitation clause below applies most to `cross_venue_disagreement`:
if fewer than 5 confirmed cases exist, record the shortfall in the manifest and
ship the corpus anyway. A genuinely hard 90 beats a padded 100.

### 2. Evidence is mandatory, not optional

`evidence.jsonl` being empty is the single largest gap. v0.2 requires **evidence coverage on 100% of cases**, frozen independently of labels.

Evidence row schema (`arbiter.holdout-evidence.v2`):

```json
{
  "case_id": "polymarket-0x...",
  "evidence_id": "ev-001",
  "observed_at": "2026-06-14T18:02:11Z",
  "source_url": "https://www.bls.gov/news.release/cpi.nr0.htm",
  "source_class": "primary|secondary|venue|aggregator",
  "claim": "CPI-U rose 0.2 percent in May on a seasonally adjusted basis",
  "value": {"kind": "number|boolean|string|date", "raw": "0.2", "unit": "percent"},
  "retrieved_payload_sha256": "sha256:...",
  "supersedes": null,
  "superseded_by": "ev-004",
  "is_revision": false
}
```

Three fields carry the weight and have no v0.1 equivalent:

- **`observed_at`** separate from `retrieved_at`: makes timing risk measurable rather than asserted.
- **`supersedes` / `superseded_by`**: encodes revision chains. A system that resolves on a superseded observation is wrong in a way v0.1 cannot detect.
- **`source_class`**: lets the scorer test whether Arbiter privileges the source the contract named over a faster aggregator.

Evidence must be collected from the source as of resolution time, not reconstructed from the outcome. Any evidence row whose only provenance is the venue's own settlement notice is `source_class: "venue"` and is excluded from blind resolution input — it leaks the label.

### 3. Gold labels are independent of venue outcomes

v0.1 treats the venue outcome as truth (`known_outcome` from the Kalshi settled endpoint). For `cross_venue_disagreement` that is incoherent — the venues disagree, so at most one is truth.

v0.2 labels carry both:

```json
{
  "case_id": "...",
  "venue_outcome": "YES",
  "counterparty_venue_outcome": "NO",
  "gold_outcome": "NO",
  "gold_rationale": "Contract names official confirmation; the announcement cited was a party statement, not the named source.",
  "gold_reviewer": "reviewer-id",
  "gold_reviewed_at": "2026-09-2xT..",
  "gold_confidence": "high|medium|low",
  "defensible_hold": true
}
```

`defensible_hold: true` marks cases where HOLD is the correct answer and forcing YES/NO would be wrong. This is the metric that matters most commercially: the deck's claim is that AI stays advisory and the governed core refuses to overstep. A corpus with no correct-HOLD cases cannot demonstrate that.

Two reviewers per case on `disputed` and `cross_venue_disagreement`; disagreements recorded, not resolved by tiebreak.

### 4. Metrics that v0.1 could not produce

Primary:

- **Correct-HOLD rate** on `defensible_hold` cases. Target: high. This is the product's core safety claim.
- **False-confident rate**: cases where Arbiter returned YES/NO and gold says HOLD was correct. Target: near zero. This is the number that kills a pilot if it is not near zero.
- **Cross-venue adjudication accuracy**: on the 15 disagreement cases, does Arbiter's verdict match gold — and does its trace cite the rule clause that distinguishes them?
- **Revision handling**: on `revised_source`, does resolution use the superseding observation?

Secondary:

- Evidence coverage (should be 100% by construction; if not, the freeze failed).
- Source-precedence accuracy on `multi_source_conflict`.
- Control-class parity vs v0.1.

Explicitly *not* a headline metric: aggregate YES/NO accuracy. On a corpus selected for hardness it is uninterpretable, and optimizing it pushes toward confident guessing, which is the failure mode this corpus exists to catch.

## Tooling changes required

`scripts/collect_holdout_candidates.py`

- Add `--hardness-class` and per-class limits; drop the implicit reliance on one bulk `status=settled` page.
- Add a cross-venue join: normalize event descriptors across Kalshi and Polymarket, emit candidate pairs where outcomes differ.
- Add a rules-quality filter that rejects boilerplate. `--min-rules-chars 40` is not sufficient — the Kalshi trademark disclaimer passes it. Reject rows whose rules text matches a known-boilerplate corpus and contain no resolution verb ("resolves", "settles", "determined by", "according to").
- Keep collection separate from freezing, as now.

`scripts/freeze_holdout.py`

- Enforce per-class quotas rather than `deterministic-stratified-round-robin` over an undifferentiated pool.
- Fail the freeze if `evidence.jsonl` is empty or coverage is below 100%.
- Fail the freeze if any evidence row has `source_class: "venue"` and is not excluded from blind input.
- Emit `categories` populated from hardness class, never `uncategorized`.

`scripts/verify_holdout.py`

- Add leakage check: no `gold_rationale`, `counterparty_venue_outcome` or venue-class evidence reachable from blind input.
- Add revision-chain integrity check: `supersedes` / `superseded_by` form a DAG with no cycles and no dangling ids.

`scripts/run_holdout.py`

- No change to the blind contract. It already loads only contracts + evidence and never opens labels. That discipline is why v0.2 is worth building.

`scripts/generate_benchmark_report.py`

- Add the four primary metrics above, reported per hardness class rather than only in aggregate.

## Sequencing

1. Cross-venue join in the collector, and hand-curate the 15 `cross_venue_disagreement` cases. This alone is a demonstrable artifact and can be shown before the rest exists.
2. Evidence schema + freeze-time coverage enforcement.
3. Remaining hardness classes and gold review.
4. Freeze, verify, blind run, score.

Step 1 is the one worth doing first regardless of whether the rest gets built. "Two regulated venues resolved the same event differently, here is what Arbiter says and why" is the entire pitch in one artifact.

## Honest limitation

Hard cases are rare, and the classes above are rare by construction. 100 cases meeting these criteria may not exist in the public settled history of two venues within a reasonable window. If a class cannot be filled, record the shortfall in the manifest rather than backfilling with easy cases. A 60-case corpus that is genuinely hard is worth more than 100 cases padded with strike ladders — which is, precisely, the v0.1 lesson.
