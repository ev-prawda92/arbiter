# Hosted read-only demo

Arbiter can run as a public, read-only console for prospects. Set
`ARBITER_DEMO_MODE=1` and point `ARBITER_DATABASE_PATH` at a database built by
`scripts/seed_demo.py`.

## Deploy on Render

1. Push the repository to GitHub.
2. In Render, choose **New > Blueprint** and select the repository. Render reads
   `render.yaml` and creates the `arbiter-demo` web service from the `Dockerfile`.
3. Deploy. On each start the container seeds `/app/backend/data/demo.db`
   (about two seconds, no network) and starts the app. Render checks
   `/api/health`, which reports `"demo_mode": true`.

Fly.io and Railway work the same way: build the `Dockerfile`, set
`ARBITER_DEMO_MODE=1` and `ARBITER_DATABASE_PATH=/app/backend/data/demo.db`, and
use the same start command as `dockerCommand` in `render.yaml`
(`python /app/scripts/seed_demo.py --db /app/backend/data/demo.db --force`, then uvicorn).
Use `/api/health` as the health check.

## Reseed

The database is rebuilt on every start, so restarting or redeploying the service
reseeds it. Locally:

```
python3 scripts/seed_demo.py --db backend/data/demo.db --force
ARBITER_DEMO_MODE=1 ARBITER_DATABASE_PATH=backend/data/demo.db python3 -m uvicorn app.server:app --app-dir backend
```

The seed ingests the committed Sep 24 2026 captures
(`tests/fixtures/venue_scan_2026-09-24.json.gz`,
`tests/fixtures/kalshi_triage_2026-09-24.json.gz`), records one example ruling on
the Xi-succession pattern labelled "Example ruling recorded for this demo; not a
venue decision.", and verifies the audit chain.

## Safety properties

- **Read-only.** Every POST, PUT, PATCH and DELETE under `/api/` returns 403
  `{"detail": "This is a read-only demo of Arbiter."}`, except three pure queries
  the console needs: `/api/ask`, `/api/decisions/consistency` and
  `/api/decision-precedents`. None of them writes to the database or the audit chain.
- **No network.** Live market and weather feeds are disabled; everything that
  would call a venue or model provider is a write endpoint and is refused.
- **No keys.** The demo needs no venue, model or cloud credentials. Do not set any.
- **Public sample data only.** The data is a snapshot of public Kalshi and
  Polymarket markets. The built-in sample markets are not shown.

`scripts/demo_mode_gate.py` asserts these properties and runs with the other gates.
