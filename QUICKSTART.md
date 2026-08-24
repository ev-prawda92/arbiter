# Quick Start

## One command to run everything

```bash
cd arbiter
./start.sh
```

Then open **http://localhost:8000** in your browser.

That's it. The script installs dependencies, builds the frontend, and starts the server.

## What you'll see

- **Markets view** (default): A docket of 10 sample Kalshi-shaped markets, each scored on three levers and stamped with a verdict (AUTO-RESOLVE, MONITORED, or HOLD).
- **Monitoring view**: Platform-level intelligence — where disputes cluster, which categories need stricter rules.
- **Policy view**: The current adjudication policy (weights, thresholds) and a changelog of every policy change.
- **Analyze button**: Paste any market question and resolution criteria, Arbiter scores it live on the same three levers.

## Sample scores

The engine scores these 10 markets as:
- **4 auto-resolve clean** (weather observations, simple price thresholds)
- **5 monitored** (macro data with some definition ambiguity)
- **1 held for review** (ceasefire market — interpretive terms, no authoritative source, no snapshot rule)

The ceasefire market is the **centerpiece**: it shows why Arbiter exists. A contract that can't resolve cleanly under the rules gets *held before payout*, not disputed after.

## Next steps for a Kalshi pitch

1. **Replace sample markets** with real Kalshi markets (via API or scraping)
2. **Include the Jan 2026 shutdown market** (settled ~13 hours apart on the same source — the key example)
3. **Build the economic argument**: disputes prevented × notional held × reputational de-risking
4. **Wire live Kalshi contract URLs** into the analyzer

## If something doesn't work

**Port 8000 already in use?**
```bash
cd arbiter/backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 9000
```
Then go to http://localhost:9000.

**Dependencies not installing?**
```bash
pip3 install --break-system-packages fastapi uvicorn httpx
cd arbiter/frontend
npm install
npm run build
cd ../backend
python -m uvicorn app.main:app
```

**Frontend not updating?**
```bash
cd arbiter/frontend
npm run build
cd ..
./start.sh
```

## Architecture in 60 seconds

- **Frontend** (React): Docket view, detail panel, monitoring dashboard, policy history
- **Backend** (FastAPI): Scoring engine (deterministic heuristics), policy store, data feeds, API
- **Scoring engine**: 100% rule-based. Source, timing, definition levers scored independently, then weighted and composited into a verdict
- **Data**: Sample markets in `backend/data/`, can swap for live Kalshi API
- **Policy**: Versioned and logged. Weights and thresholds live in `backend/data/policy.json`

## Files you'll want to edit

- `backend/app/engine.py` — scoring rules (AUTHORITATIVE_SOURCES, TIME_PATTERNS, INTERPRETIVE_TERMS)
- `backend/app/policy.py` — lever weights and verdict thresholds
- `backend/data/sample_markets.json` — docket content
- `frontend/src/main.jsx` — React components (docket, detail, monitoring, analyze modal)
- `frontend/src/styles.css` — design system

## To connect to real Kalshi markets

Edit `backend/app/feeds.py`:
```python
def get_markets(limit=40, live=True):
    if live:
        try:
            return _kalshi_live(limit)  # ← tries this first
        except:
            return _sample(...)  # ← falls back to sample if unreachable
```

Set `KALSHI_API_KEY` env var and the live feed will work.

## API endpoints (for reference)

```
GET  /api/health              health check
GET  /api/markets             all scored markets
GET  /api/markets/{ticker}    single market + resolution trail
GET  /api/monitoring          platform intelligence
GET  /api/policy              current policy + changelog
POST /api/policy              update policy (logged)
POST /api/analyze             score arbitrary pasted contract
```

Hit `/api/health` to make sure the backend is running.

## Good luck

The app is a full working prototype. The scoring is real, the verdicts are defensible, and the design is institutional-grade. Everything is transparent. Take it to Kalshi's compliance team.
