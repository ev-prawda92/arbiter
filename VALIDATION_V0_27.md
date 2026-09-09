# Validation — Arbiter v0.27.0

## Release-gate addition

`real_benchmark_gate.py` validates the benchmark protocol using isolated fixture data. Fixture results are engineering tests only and are never presented as real-contract benchmark performance.

The gate covers:

- real-benchmark posture and certification boundary
- Kalshi/Polymarket payload normalization
- binary terminal-outcome filtering
- raw payload hashing
- deterministic stratified selection
- immutable freeze behavior
- separate contract/label/provenance files
- aggregate and per-file hash verification
- label leakage prevention
- blind run label-separation attestation
- evidence-label separation and evidence hash pinning
- deterministic numeric evidence-backed resolution
- governed HOLD behavior for non-READY cases
- prediction hash pinning
- run/dataset/evidence hash linkage
- post-run report generation
- evidence-backed outcome agreement and hold-rate reporting
- explicit gold-label coverage
- tamper detection

Expected release gate after v0.27 integration:

```text
RELEASE GATE: PASS — 452/452 checks across 18 suites
```

That number remains internal engineering validation. It is not an independent accuracy or production certification claim.
