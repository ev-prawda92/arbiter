# Arbiter v0.38 — Repository Hardening

No product behavior changes. This release makes the codebase easier to review, run and trust.

## Structure
- Repository root reduced to entry points. Release notes moved to `docs/releases/`; product,
  operations and benchmark documents to `docs/product/`, `docs/operations/`, `docs/benchmark/`.
- `CHANGELOG.md` indexes every release.

## One version
- `VERSION` is the single product version. `backend/app/version.py` and `frontend/package.json`
  match it, enforced by `tests/test_repo_consistency.py`.
- The API previously reported `0.27.0` from four hard-coded strings; it now reports the real version.
- Hard-coded version labels removed from the workbench and case workspace UI.

## Safety
- Settlement signing fails closed in production: with `ARBITER_ENV=production` and no
  `ARBITER_SETTLEMENT_SIGNING_SECRET`, Arbiter refuses to sign rather than using the development key.
  Covered by three behavioral tests.
- `backend/data/policy.json` is runtime state and no longer committed (the committed copy carried
  23 no-op version entries). Location is configurable with `ARBITER_POLICY_PATH`; the app seeds it
  from `DEFAULT_POLICY` on first run.

## Tooling
- Dependencies pinned (`backend/requirements.txt`); dev tools in `backend/requirements-dev.txt`.
- `pyproject.toml` configures ruff and pytest. Lint is clean: 14 unused imports and 3 dead
  variables removed (each checked by hand; none hid a bug). Python formatted with `ruff format`;
  five minified stylesheets expanded with prettier.
- `Makefile`: `make install`, `make lint`, `make test`, `make gates`, `make check`.
- CI runs lint, format check and pytest ahead of the gates.
- Proprietary `LICENSE` (Operation Mincemeat LLC).

## Validation
- All 26 gate scripts pass; full release gate 452/452 across 18 suites; public API gate PASS.
- pytest 24/24. Frontend builds.
