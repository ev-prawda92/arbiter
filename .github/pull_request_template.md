## Summary

Describe what changed and why.

## Product / governance impact

- [ ] No change to resolution semantics
- [ ] Changes contract compilation or semantic interpretation
- [ ] Changes evidence handling
- [ ] Changes `YES / NO / HOLD` behavior
- [ ] Changes auth, tenant isolation, audit, idempotency, or settlement boundaries
- [ ] Changes benchmark or holdout behavior

Explain any checked items:

## Validation

- [ ] Relevant unit / targeted tests pass
- [ ] `python3 scripts/curation_gate.py`
- [ ] `python3 scripts/public_api_gate.py`
- [ ] `python3 scripts/release_gate.py`
- [ ] Manual validation performed where appropriate

Paste notable results or explain why a gate is not applicable.

## Security / integrity review

Confirm that this change does not introduce secrets, runtime databases, private credentials, frozen holdout labels, or generated benchmark outputs into source control.

## Known limitations / follow-up

List anything intentionally deferred.
