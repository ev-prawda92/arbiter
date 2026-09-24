# Arbiter v0.40: Unified Console

Three pages with three visual languages (home, console, decision workbench) become one
console organized around how an operator works. Backend behavior is unchanged, apart from
work items now carrying their precedent match as structured data.

## The flow

- **Today:** a single sentence says how many decisions stand between the queue and
  settlement. Below it:
  - a four-step flow strip (Intake → Queue → Decide → Precedent) with live counts
  - the patterns to decide next, precedent-covered ones first
  - controls: audit chain, held before payout, exposure
  - an activity feed that groups repeated events
- **Queue:** work patterns in a table, filterable by blocker family and by precedent
  coverage. Each row expands to its cases, with a direct path to Decide. The item-level queue
  is one tab away ("Every case").
- **Decide:** the workbench, rebuilt as three steps (Understand → Precedent → Rule).
  - The affected cases are visible.
  - The live consistency check and the distinguish/overrule controls are kept.
  - After recording, a result card shows queue before → after and the precedent status,
    and leads straight to the next pattern.
- **Precedents:** the record, with each ruling's clauses, decided contracts and the
  contracts it has applied to since. Appeal checks and a prominent Ask Arbiter with example
  questions are on this page.
- **Ask Arbiter** sits in the top bar on every page (⌘K). Answers cite and link to precedents.

## Consistency

- One set of design tokens (slate, with status colors per blocker family).
- Detailed views from the old home app (Markets, Contract review, Portfolio, Benchmark,
  Controls & audit, Validation, Policy) render inside the shell. Their stylesheet is scoped
  under `.legacy` and retinted through the shared tokens.
- `console.html` and `decision-workbench.html` redirect to `/#/queue` and `/#/decide`.
- Superseded frontend code removed: the old console, its case workspace, and the standalone
  workbench (17 files).
- Works at phone width: collapsible navigation, and no horizontal page scroll on any section
  (checked at 390px).

## Validation

- Every section rendered and checked in a browser, desktop and phone.
- The full decide flow was clicked through: Today → precedent-covered pattern → Follow →
  seven cases cleared → next pattern.
- `make check`: lint, format, tests and all 27 gates, release gate 452/452.
