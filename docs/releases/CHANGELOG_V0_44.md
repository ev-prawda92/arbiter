# Arbiter v0.44: Hosted Demo Mode

The console can now be deployed publicly as a read-only demo for prospects.

- **`ARBITER_DEMO_MODE=1`** makes the API read-only: every write returns 403 with "This is a read-only demo of Arbiter." Three query-only POSTs stay open because the console needs them: `/api/ask`, `/api/decisions/consistency` and `/api/decision-precedents`. None of them writes to the database or the audit chain.
- **No network in demo mode.** The market feed returns nothing and the weather feed never calls out, so the built-in sample markets stay out of the queue.
- **A banner** in the console reads "Read-only demo · sample data from public Kalshi and Polymarket markets". `/api/health` reports `demo_mode`.
- **`scripts/seed_demo.py`** builds the demo database offline from the committed Sep 24 2026 fixtures. It records one example ruling on the Xi-succession pattern, labelled as an example and not a venue decision, then verifies the audit chain.
- **Hosting:** `render.yaml` (a Render blueprint using the Dockerfile) reseeds on start. `docs/operations/DEMO_DEPLOY.md` covers Render, Fly.io and Railway.
- **Gate:** `scripts/demo_mode_gate.py` checks that:
  - health reports demo mode;
  - the main reads return 200;
  - decisions, work-item updates, anchors, packages and engagements all return 403;
  - the audit chain is unchanged after every attempted write;
  - writes pass normally without the flag.
