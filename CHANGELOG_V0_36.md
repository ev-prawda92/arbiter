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

## Precision, tuned on a real scan

The first live dry run (Sep 23, 300 open markets) flagged 105; almost all were
false alarms. Three causes, each fixed and locked in by a gate that replays
that real scan (`tests/fixtures/venue_scan_2026-09-23.json.gz`):

- **Venue templates:** Polymarket puts "consensus of credible reporting" on
  nearly every market. Intake now learns templated wording from each scan
  (the classifier's own 35% rule) plus a known-template floor.
- **Series fine print:** Kalshi player props all say "pinch hit at bats will
  not count". Fine print shared across a Kalshi series is template, not a
  dispute (real UMA dispute rounds still count).
- **Sports vs elections:** "win the 4th quarter" is not an election. A
  contested-official-source flag now needs electoral wording.

Result on the same scan: 5 flagged (four elections and one market with a
real what-counts clarification), down from 105.

## Re-triage

    python3 scripts/sync_venues.py --retriage --no-sync --dry-run
    python3 scripts/sync_venues.py --retriage --no-sync

Closes open intake work the current classifier no longer flags, with the
reason audited. Never touches work an operator moved, a decision covers, or a
watchlist pinned to a review class.

## Workbench

The decision workbench now says up front when a decision cannot clear a
pattern (payout hold, audit break, missing evidence, monitoring) and why; the
button reads "Record decision (cases stay open)" instead of promising a clear.

## Validation

- New Venue Intake gate (offline; includes the real-scan replay and re-triage) in CI.
- Decision Clearing gate extended (C9: per-pattern clearability).
- All gates pass; full release gate 452/452.
