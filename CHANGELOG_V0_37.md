# Arbiter v0.37 — Kalshi Discovery by Category

v0.36 discovery scanned Kalshi's flat list of open markets. On Sep 23 2026 the
first 1,000 were all sports props, so politics, economics and world-event
markets, where MOU-style interpretive questions live, were never reached.

v0.37 walks Kalshi's open **events** instead. Each event carries a category and
nests its markets, and the events list leads with non-sports events (World,
Elections, Politics, Economics, Science and Technology, Climate and Weather...).

## Run it

    python3 scripts/sync_venues.py --discover 500 --dry-run
    python3 scripts/sync_venues.py --discover 500 --kalshi-categories "Politics,Elections,World,Economics" --dry-run

- Sports is excluded by default (`--kalshi-exclude`, comma-separated).
- `--kalshi-categories` restricts to an allow-list (case-insensitive).
- `--kalshi-source markets` keeps the old flat scan.
- Output now shows flagged/scanned per Kalshi category.

## Details

- Cursor paging across both Kalshi hosts, de-duplicated by ticker; parlays,
  rule-less and non-open markets skipped.
- Kalshi's category filter and series filter on `/series` and `/markets`
  appeared to be ignored when checked on Sep 23, so filtering is done on the
  event's own category field, client-side.
- A flagged event's work pattern is labelled with the event title ("Who will
  be the next Secretary General of NATO?") rather than one market's title.
- Nested markets without `event_ticker` are grouped by ticker prefix.

## Validation

- Venue Intake gate V16: paging, host de-duplication, category allow/deny,
  parlay/closed/rule-less skipping, one-event clarification flagged as one
  pattern, per-category counts.
