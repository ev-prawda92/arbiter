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

## Precision on the first category scan (Sep 24)

The first event-based scan flagged 305 of 500 Kalshi markets in 27 events.
Reading the rules text of each flagged group found four causes, all fixed:

- **Rules that pin the release.** Long-dated GDP / CPI / unemployment markets
  say "Later revisions will not affect the outcome" or "The initially reported
  value will be used". No revision question is left, so no flag.
- **Substring matches.** "Zuppi" contained "ppi" (Producer Price Index).
  Revision-prone series now match as whole words.
- **Succession is not an election.** "Next Prime Minister of Romania" or "the
  President of Kenya leaves office first" needs electoral wording (election,
  ballot, referendum...) to be flagged as a contested official source, and
  that wording must be outside standing fine print: Kalshi's shared definition
  of "formally holds" a role ("appointment, election, succession...") is template.
- **Fine print learning now covers vague-source wording too**, and a
  multi-word proper name ("Chair of the Democratic National Committee") is one
  unit when comparing sentences across events.

Same scan now: 22 Kalshi markets in 3 events (next CCP leader "announced by
the party or credible sources"; first G7 leader out, with a sole-discretion
death clause; BRUV winning a Commons seat) and 3 Polymarket markets. The Sep
23 scan still flags exactly its 11.

## Validation

- Venue Intake gate V17 replays the real Sep 24 scan
  (`tests/fixtures/venue_scan_2026-09-24.json.gz`) and pins the 25 flags.
- Venue Intake gate V16: paging, host de-duplication, category allow/deny,
  parlay/closed/rule-less skipping, one-event clarification flagged as one
  pattern, per-category counts.
