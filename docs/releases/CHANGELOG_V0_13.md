# Arbiter v0.13 — Semantic Contract Intelligence

Arbiter v0.13 introduces a first-class semantic interpretation layer before deterministic resolution.

## New

- `backend/app/semantic_contract.py`
  - domain concept recognition
  - plain-language concept explanations
  - semantic field extraction
  - ambiguity detection
  - clarification questions
  - stable semantic analysis hashes
- `POST /api/semantic-analyze`
- Compiler v0.1.3 embeds semantic analysis in every compilation result.
- Resolution Compiler UI now surfaces Semantic Contract Intelligence, recognized concepts, and unresolved meaning.
- `scripts/semantic_gate.py` validates the semantic layer end-to-end.

## Initial ontology coverage

- Consumer Price Index / inflation contracts
- Federal Reserve / FOMC policy-rate contracts
- weather observation contracts

## Important boundary

Semantic findings are **advisory in v0.13** while the ontology and false-positive behavior are benchmarked. Existing deterministic compiler gates remain binding and backward-compatible. Arbiter never invents missing contractual meaning.

The intended architecture is:

**AI/semantic interpretation → governed Resolution Specification → evidence → deterministic resolution → approval → settlement authorization → audit.**
