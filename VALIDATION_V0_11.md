# Arbiter v0.11 Validation

## Required release gates

```bash
python3 scripts/coherence_test.py
python3 scripts/enterprise_gate.py
python3 scripts/evidence_gate.py
```

Expected baselines:
- Coherence: 48/48 PASS
- Enterprise: 14/14 PASS
- Active Evidence: 27/27 PASS

## Active Evidence behaviors covered
The v0.11 gate creates isolated test authorities/contracts and verifies monitor creation, initial evidence capture, duplicate idempotency, append-only revisions, reevaluation requests, cross-authority conflicts, Work Queue escalation, source outages, retry/backoff, source health, evidence provenance hashes, infrastructure summaries, and audit-chain integrity.

These are software validation results, not a penetration test, SOC 2 opinion, or certification of production settlement readiness.
