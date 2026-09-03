# Arbiter v0.9.1 — Compiler Integration Fix

- Fixed live contract review so the submitted resolution criteria, not the previously selected market criteria, are displayed in the result panel.
- Preserved compiler and design-review output when moving from the compiler modal into the Resolution workspace.
- Added compiled Resolution Specification status/details to the live result panel.
- Added conservative title-to-rules topic consistency validation. Clear cross-domain mismatches (for example a CPI title paired with shutdown rules) now BLOCK compilation with `contract.title_rules_mismatch`.
- No change to binding resolution authority: compiler output remains a proposal and deterministic governed resolution remains the adjudication boundary.
