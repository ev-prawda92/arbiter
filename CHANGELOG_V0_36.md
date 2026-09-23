# Arbiter v0.36 — Live Venue Intake

Until now, markets entered Arbiter by hand. v0.36 pulls them from Kalshi and
Polymarket directly and routes the ones that need a human judgment into the
work queue, where v0.35 decisions can clear them.

## Run it (from a machine that can reach the venue APIs)

    python3 scripts/sync_venues.py --discover --dry-run
    python3 scripts/sync_venues.py --discover
    python3 scripts/sync_venues.py --watchlist benchmarks/seeds/dual_listed_seeds_v0_2.jsonl

`--discover` scans currently open markets on both venues (Kalshi: both API
hosts, parlays skipped) and keeps only those the deterministic hardness
classifier flags. `--watchlist` syncs specific markets. Both write to the
app's database; `--dry-run` writes nothing; `--save-raw DIR` keeps every raw
API response.

## What intake does (`backend/app/venue_intake.py`)

- **Contracts:** one per market, versioned when the venue's rules text changes.
- **Evidence:** hashed from the full raw API response; appended only when
  status, outcome, rules or dispute count change (not on price ticks), each
  new record superseding the last.
- **Triage:** interpretive wording and disputes -> policy interpretation;
  revision-prone data -> timing revision; contested official sources ->
  authority conflict; late/void settlement -> operator review. Markets on the
  same event form one work pattern, so one decision can clear them together.
- **Cross-venue:** if both venues settle an event differently, a critical
  work item opens.
- **Settlement:** a market that settles closes its own intake work item with
  the venue's outcome.
- **Never reopens work:** once a work item exists, its state belongs to
  operators and governed decisions, not to the sync.

## Workbench

The decision workbench now says up front when a decision cannot clear a
pattern (payout hold, audit break, missing evidence, monitoring) and why; the
button reads "Record decision (cases stay open)" instead of promising a clear.

## Validation

- New Venue Intake gate (25 checks, offline fixtures) in CI.
- Decision Clearing gate extended (C9: per-pattern clearability).
- All gates pass; full release gate 452/452.
