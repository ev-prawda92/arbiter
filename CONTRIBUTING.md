# Contributing to Arbiter

Thank you for your interest in Arbiter.

Arbiter is resolution infrastructure for outcome-based contracts. The project is designed around a strict boundary: AI may interpret and recommend, but governed evidence, deterministic logic, explicit controls, and human review remain responsible for consequential resolution decisions.

## Development workflow

1. Create a feature branch from `main`.
2. Keep changes focused and avoid mixing product work with unrelated refactors.
3. Add or update tests for behavior changes.
4. Run the relevant local gates before opening a pull request.
5. Open a pull request with a clear description of scope, risks, and validation performed.

For changes touching the current public Resolution API and benchmark pipeline, run:

```bash
python3 scripts/curation_gate.py
python3 scripts/public_api_gate.py
python3 scripts/release_gate.py
```

The public API gate expects the standalone public API on port `8001`. The full release gate expects the main Arbiter application on port `8000`.

## Engineering principles

- Fail closed when contract semantics, authority, timing, or evidence are insufficient.
- Preserve `YES / NO / HOLD`; never force a binary answer when the governed system should HOLD.
- Keep AI outputs advisory unless a specific, reviewed design explicitly promotes them into a governed control.
- Preserve auditability, deterministic replay, tenant isolation, and idempotency.
- Do not use frozen holdout labels for tuning, training, prompt optimization, or development decisions.
- Treat benchmark integrity and benchmark validity as separate properties.
- Avoid committing runtime databases, secrets, local credentials, frozen benchmark labels, or generated run artifacts.

## Pull requests

A pull request should include:

- what changed and why;
- any public API or schema changes;
- security or governance implications;
- tests and release gates run;
- known limitations or follow-up work.

Prefer small, reviewable pull requests. Squash merging is recommended for feature branches unless preserving individual commits adds clear value.

## Security issues

Please do not open public issues for suspected vulnerabilities. Follow the process in `SECURITY.md`.
