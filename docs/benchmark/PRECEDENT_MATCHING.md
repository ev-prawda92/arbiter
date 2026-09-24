# Precedent matching: method and measured results

Arbiter v0.39 turns every governed decision into a precedent and checks each
new contract against it. This page covers how a match is made, how the thresholds
were chosen, and what they achieve on real markets. Reproduce everything here with:

```bash
python3 scripts/precedent_eval.py
```

## What a precedent is

A precedent is built from a decision record. It carries:

- **The ruling:** selection, governing rule and rationale.
- **The decided contracts:** full rules text for each.
- **The clauses ruled on:** the sentences in those contracts that the ruling
  resolves. Which sentences count depends on why the contracts were flagged:
  - interpretive criteria → "credible", "permanent", "sole discretion"…
  - disputed → venue clarifications ("does not count as"…)
  - multi-source conflict → official / certified / consensus wording
  - revised source → revision and release wording
  - late or void → void / cancel / postpone wording

Clauses are normalized (proper names → `<x>`, numbers → `<n>`), so the same
clause compares equal across events.

## How a new contract is matched

| Tier | Test | Meaning |
|---|---|---|
| `same_clause` | clause similarity ≥ 0.85 | The clause that was ruled on is in this contract. The ruling applies. |
| `same_template` | contract similarity ≥ 0.80 | Same contract template (e.g. next event of the series). The ruling likely applies. |
| `related` | either similarity ≥ 0.60 | Shown for context. Never enforced. |

**Contract similarity** is 0.7 × TF-IDF cosine of the title and rules (unigrams and
bigrams, numbers masked) plus 0.3 × TF-IDF cosine of the normalized title shape.
IDF is computed over every contract Arbiter knows, so wording that recurs on every
contract weighs little.

**Clause similarity** is the token cosine of the normalized clauses, with exact
normalized equality scoring 1.0.

A clause the venue uses as standing fine print (learned per scan: recurring across
2+ events and 3+ markets) never carries a ruling.

Only the two applicable tiers drive consistency checks. Everything is
deterministic: no model, no hidden score. Every match reports its tier, both
similarities, the closest decided contract, and the matched clause pair.

## Results on real markets

Data: the recorded live scans of Sep 23 and Sep 24, 2026 (Kalshi + Polymarket),
838 distinct open markets.

### Cross-event template transfer

Ground truth is the **template family**:
- **Kalshi:** the series ticker with period digits collapsed, so KXNCAAF2QTOTAL and
  KXNCAAF3QTOTAL are one family.
- **Polymarket:** the normalized title shape.

The test set is the 20 families that appear in 2+ events, covering 491 markets. For
each market, its own event is hidden and the best match from any other event is
taken.

| Threshold | Recall | Precision | Markets with no family over threshold |
|---|---|---|---|
| 0.60 | 490/491 = 0.998 | 1.000 | 90 / 347 |
| 0.70 | 474/491 = 0.965 | 1.000 | 62 / 347 |
| 0.75 | 456/491 = 0.929 | 1.000 | 5 / 347 |
| **0.80 (same_template)** | **391/491 = 0.796** | **1.000** | **5 / 347** |
| 0.85 | 356/491 = 0.725 | 1.000 | 2 / 347 |
| 0.90 | 335/491 = 0.682 | 1.000 | 0 / 347 |

- **Wrong-family top matches at any score:** none.
- **The 5 markets without a family match that still score ≥ 0.80.** On review, all
  5 are the same template under a different ticker. They are pinned in the gate.
  - KXPERSONPRESFUENTES-45 ↔ KXPERSONPRESMAM-45 ("Will … become President of the
    United States before 2045?")
  - Polymarket 4873310 → 4782237 (the highest-temperature template, Amsterdam and Madrid)
  - Polymarket 3866284 ↔ 4844895 (the "hit (HIGH) $…" template, Netflix and NVIDIA)

0.80 was chosen as the lowest threshold that keeps unrelated markets out. At 0.75
the 5 no-family hits are the same, but at 0.70 unrelated same-player markets
(e.g. "2+ RBIs" against "3+ hits") start to appear.

### Clause reach

Each of the 10 flagged events is treated as decided, and its ruled clauses are
matched against every market in every other event. Exactly two links appear, and
both were reviewed as correct applications:

- Polymarket event 834406 → polymarket:3697620
- Polymarket event 870884 → polymarket:3519811

Both share the clause *"The primary resolution source for this market will be the
official results of … as published by the state electoral authority …"*. A ruling
on official results versus early reporting for one election applies to the other.

## Limits

- **Two days of data.** Thresholds were set on two scans a day apart. They should
  be re-measured as scans accumulate: `precedent_eval.py` runs on any recorded scan.
- **Few cross-event clause links.** The clause-level evidence here is two links.
  The gate also proves the mechanism end to end on a synthetic next event, built by
  re-dating the real G7 markets. It does not show how often real venues repeat a
  ruled clause.
- **Recall at the enforced tier is 80%.** About 1 in 5 next-event markets fall
  below `same_template` and are shown only as `related`. A precedent is never
  silently lost, but it is not enforced on those markets.
- **Agreement is word overlap.** "Consistent" and "divergent" compare the
  selection text by word overlap (Jaccard ≥ 0.5). Following a precedent through
  the workbench copies its wording, so this is reliable in practice. Free-text
  rulings that say the same thing in different words can read as divergent. The
  operator then records a distinction, which is audited.
