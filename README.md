# Arbiter

**A market operations and resolution console for event-contract exchanges.**

Arbiter reads live markets from Kalshi and Polymarket and finds the few that will need a human
judgment when they resolve: contested wording, conflicting official sources, data that gets
revised. It puts them in one work queue. An operator records one governed decision, and that
decision clears every case it answers. Each decision becomes precedent: when the next
contract with the same clause or template arrives, Arbiter shows the ruling that
applies, and departing from it requires a stated distinction or an explicit overrule.
Each step lands in a hash-chained audit trail.

> AI interprets. Policy governs. Evidence proves. Deterministic logic resolves. Humans handle exceptions.

## Run it

Requires Python 3.11+ and Node 22.

```bash
./start.sh
```

Then open `http://localhost:8000`. One console, organized around the operator's day:

| Section | What it is |
|---|---|
| **Today** | What stands between the queue and settlement: the intake → queue → decide → precedent flow with live counts, what to decide next, controls, activity |
| **Queue** | Open cases grouped into work patterns by root cause, filterable, with precedent coverage marked |
| **Decide** | One pattern at a time: the judgment needed, what was ruled before (clause by clause), the ruling with a live consistency check, then straight on to the next pattern |
| **Precedents** | Every ruling, what it has applied to since, appeal checks, and Ask Arbiter |
| Markets, Contract review | Per-contract resolution detail and pre-listing design review |
| **Audit trail** | For compliance and outside auditors: any contract's full lineage, the searchable log, exceptions (departures from precedent, manual closes, self-approval), anchor receipts, auditor engagements (reproducible sampling, tested working papers, findings, signed attestation report), and an evidence package verified independently with `tools/arbiter-verify` |
| Portfolio, Benchmark, Controls & audit, Validation, Policy | Assurance views |

Ask Arbiter is in the top bar on every page (⌘K).

Pull live venue markets into the queue (run from a machine that can reach the venue APIs):

```bash
python3 scripts/sync_venues.py --discover 500 --dry-run
python3 scripts/sync_venues.py --discover 500
```

A typical scan of 500 open Kalshi markets flags about 20 for human review. The rest resolve
mechanically and stay out of the queue. Every scanned market is also checked against
precedent, and a market carrying a clause a human already ruled on comes in with that
ruling attached.

How well precedent matching works on real markets, and how to reproduce it:
[docs/benchmark/PRECEDENT_MATCHING.md](docs/benchmark/PRECEDENT_MATCHING.md).

## How it fits together

```mermaid
flowchart LR
  V[Kalshi / Polymarket APIs] --> I[Venue intake<br/>normalize + hardness classifier]
  I --> S[(Resolution store<br/>SQLite / Postgres<br/>hash-chained audit)]
  S --> E[Resolution engine<br/>Source · Timing · Definition]
  E --> Q[Operations intelligence<br/>clusters by root cause]
  Q --> W[Work queue]
  W --> D[Decision records<br/>governed, versioned]
  D -->|clears answered cases| W
  D --> P[Precedent engine<br/>clauses + templates]
  P -->|arrival check| I
  P -->|consistency: follow / distinguish / overrule| D
  P --> K[Ask Arbiter<br/>cited answers]
  D --> A[Approvals + settlement handoff<br/>signed packets]
```

Details: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## How it's tested

```bash
make install
make check
```

`make check` runs lint, format check, unit and consistency tests, then starts the app and the
public API on throwaway databases and runs all 29 gate scripts, including the full release gate
(**452 checks across 18 suites**). CI runs the same on every pull request.

## Status

Arbiter runs end to end on live venue data locally. It is **not** certified for production
settlement. The benchmark report states `production_settlement_certified: false`, and it stays that way until an external security review,
penetration test and deployment-backed resilience evidence exist. What is production-shaped,
what is a reference implementation, and the known limits are in
[docs/DILIGENCE.md](docs/DILIGENCE.md).

## Repository

| Path | Contents |
|---|---|
| `backend/app/` | FastAPI service, engines, stores |
| `frontend/` | React + Vite UI (three entry pages) |
| `scripts/` | Gate scripts, venue sync, benchmark tooling |
| `tests/` | pytest suite and recorded venue scans |
| `benchmarks/` | Benchmark seeds and frozen datasets |
| `demo/` | Worked case run through the real engine |
| `deploy/` | Deployment templates |
| `docs/` | Architecture, diligence, API, product, operations, releases |
| `CHANGELOG.md` | Every release, newest first |

Copyright (c) 2026 Operation Mincemeat LLC. All rights reserved. See [LICENSE](LICENSE).
