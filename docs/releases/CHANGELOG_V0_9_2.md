# Arbiter v0.9.2 — Resolution Gate Coherence

## Coherence fixes
- Compiler `BLOCK` now dominates resolution state: live analysis returns `HELD`, never `PENDING` or auto-resolution eligible.
- Compiler `REVIEW` now requires governed human review before automated resolution.
- `/api/analyze` returns integrity analysis, compilation, and gated resolution in one atomic response.
- Frontend consumes that single response, preventing split-brain state between compiler and resolver.
- Title/rules mismatch causes compilation to trust the governing rules only; title-derived authority/definition fields are not treated as trusted.
- Compiler exposes field trust metadata.
- Source scoring recognizes “first published release” as an explicit revision policy.

## Invariant
`BLOCK > REVIEW > READY` is the controlling pre-resolution gate. Intelligence may explain or score risk, but cannot bypass it.
