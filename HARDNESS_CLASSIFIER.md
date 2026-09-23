# Hardness classifier (v0.2 tooling)

`backend/app/real_benchmark/hardness.py` + `scripts/classify_hardness.py`.
Buckets a bulk candidate pool into v0.2 hardness classes deterministically, so
the corpus scales without hand-picking every case.

## Run

    python3 scripts/collect_holdout_candidates.py --venue kalshi --venue polymarket --limit-per-venue 400 --out benchmarks/candidates_v0_2_raw.jsonl
    python3 scripts/classify_hardness.py benchmarks/candidates_v0_2_raw.jsonl --out benchmarks/candidates_v0_2_classified.jsonl --report benchmarks/hardness_report_v0_2.json

## What it assigns (objective classes only)

- `disputed` — Polymarket UMA dispute-round count (metadata.uma_dispute_count),
  or a venue clarification/disclaimer in the rules. The dispute count is the
  strongest signal: objective, bulk-available, and it caught Zelenskyy (5 rounds).
- `revised_source` — revision-prone series in title/rules (CPI, payrolls, GDP).
- `multi_source_conflict` — election with an "official"/"certified" named source
  (official result commonly contested). Always needs_review.
- `late_or_void` — void/canceled outcome, or settled materially after close.
- `control_easy` — a clean price/number threshold and no hard signal.
- `unclassified` — neither clearly easy nor clearly hard -> human triage.

## The interpretive decision (important)

`interpretive_criteria` is NOT auto-assigned. Four iterations on the v0.1 pool
showed lexical detection is unreliable: interpretive hardness lives in an
undefined common noun in the question ("suit", "recession"), which no lexicon
catches, while every venue/sport rules template carries its own filler
("consensus of credible reporting", "announced", "permanent") that a lexicon
false-fires on. Progression on 200 rows: 157 -> 57 -> 21 -> 11 false positives,
each fix chasing a different template word.

So interpretive is computed as an advisory `interpretive_hint` only, to guide
human triage of the `unclassified` pile -- never a primary label. The
genuinely interpretive cases that matter (Zelenskyy) are already caught as
`disputed` via the objective UMA dispute count.

Two defenses keep the objective classes clean:
1. Per-venue boilerplate: a term in >=35% of a venue's rows is templated and
   carries no interpretive weight (computed per venue, since each venue's
   template differs).
2. control_easy only stands when no hard class fired.

## v0.1 pool result (200 rows)

control_easy 122 | unclassified 73 | multi_source_conflict 3 | revised_source 2;
12 interpretive hints flagged for triage. This is honest: the v0.1 pool really
is mostly easy thresholds plus esports/sports props that need a human read.
Real hard cases come from a much larger, more topical pull -- which the patched
collector (now hitting api.elections.kalshi.com too) can finally reach.
