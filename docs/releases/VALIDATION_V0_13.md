# Arbiter v0.13 Validation

Validated on an isolated local database against the complete release-gate stack.

| Gate | Result |
| --- | ---: |
| Coherence | 48 / 48 PASS |
| Enterprise boundary | 14 / 14 PASS |
| Active evidence | 27 / 27 PASS |
| Settlement control | 30 / 30 PASS |
| Semantic contract intelligence | 29 / 29 PASS |
| **Total** | **148 / 148 PASS** |

## Semantic cases covered

The v0.13 semantic gate verifies that Arbiter:

- recognizes CPI as Consumer Price Index;
- provides a plain-language explanation;
- detects a generic CPI contract as semantically incomplete;
- flags missing CPI series, measurement basis, and reference period;
- extracts BLS and first-release semantics;
- recognizes a fully specified CPI example as semantically ready;
- extracts CPI-U, year-over-year basis, reference period, and seasonal-adjustment basis;
- recognizes Federal Reserve/FOMC rate-action contracts;
- extracts the federal funds target range and FOMC statement;
- embeds semantic analysis inside compiler output;
- preserves the existing compiler gate as binding in v0.13;
- exposes the semantic API in developer metadata.

## Claim boundary

148/148 passing release checks are evidence about the tested development build. They are not a claim of universal contract understanding, legal correctness, penetration-test completion, or production settlement certification.
