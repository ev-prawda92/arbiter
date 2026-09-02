# Arbiter v0.4 build notes

## Added
- Rebranded UI to **Resolution Intelligence Platform**.
- Contract Intelligence output on `/api/analyze`.
- Listing-readiness score and structured deficiencies.
- Deterministic drafting-fix recommendations.
- Evidence packet with contract / resolution / governance authority separation.
- SHA-256 evidence packet hash.
- `/api/portfolio` with lever pressure and top-risk contracts.
- Portfolio Intelligence UI surfaces primary risk driver and highest-risk contracts.

## Fixed
- FastAPI now serves the compiled Vite build from `backend/dist` rather than the JSX source directory.

## Preserved by design
- Deterministic engine is still binding.
- LLM remains advisory only.
- Portfolio intelligence remains read-only.
- Policy changes remain versioned and logged.
