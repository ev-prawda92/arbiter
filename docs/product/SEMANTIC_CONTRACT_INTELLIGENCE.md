# Semantic Contract Intelligence

## Purpose

Event contracts are often short natural-language rules attached to financial consequences. A phrase that looks obvious to a human can conceal multiple materially different meanings.

Example:

> Will U.S. CPI be above 3.0%?

A binding resolution may still need to determine:

- Which CPI series?
- Year-over-year, month-over-month, or index level?
- Which geography/population?
- Seasonally adjusted or not?
- Which reference month?
- Which publication date?
- Which authority controls?
- Does the first release or a later revision control?

Arbiter's Semantic Contract Intelligence layer is designed to expose those questions before money depends on an interpretation.

## Control boundary

Semantic intelligence may:

- identify real-world concepts;
- explain those concepts in plain language;
- map contract language to semantic fields;
- detect ambiguity or missing dimensions;
- propose clarification questions;
- provide provenance for interpretation.

It may **not** silently fill missing contractual terms or independently authorize settlement.

## v0.13 gate mode

Semantic findings are advisory in v0.13. This is intentional. Before semantic controls become binding, Arbiter should build a larger ontology, evaluate untouched real contracts, measure false positives/false negatives, and promote individual semantic findings through governed policy.

## Product model

Arbiter can now be described as:

> A Semantic Contract Intelligence and Resolution Control Platform for event markets.

The operational chain is:

`Natural-language contract → Semantic Contract Intelligence → Resolution Specification → Evidence → Deterministic Resolution → Approval → Settlement Authorization → Audit`
