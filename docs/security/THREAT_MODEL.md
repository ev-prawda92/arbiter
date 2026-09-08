# Arbiter Threat Model — v0.26

## Protected assets
Contract versions, resolution specifications, source/evidence records, policy versions, approval votes, settlement authorization packets, tenant identity context, model credentials, audit-chain integrity, and reference/shadow-pilot data.

## Primary trust boundaries
1. Operator/browser → Arbiter API
2. Arbiter service → PostgreSQL
3. Arbiter service → object storage
4. Arbiter service → Secrets Manager/KMS
5. Arbiter → external authoritative sources
6. Arbiter → model providers (advisory only)
7. Arbiter → venue settlement handoff

## High-priority threats
- cross-tenant data access or confused-deputy tenant override
- forged or replayed evidence
- policy or contract version substitution
- duplicate settlement authorization
- maker/checker bypass
- secret disclosure
- model output gaining binding authority
- webhook replay/signature forgery
- DB/object-store outage producing unsafe default behavior
- audit-chain tampering
- source revision ambiguity or stale evidence
- compromised operator identity or overbroad service credential

## Safety properties
Arbiter should fail closed on unresolved contract semantics, unsafe production configuration, missing signing material, invalid tenant context, failed evidence controls, stale versions, or incomplete approval requirements. AI output is non-binding.

## External review target
A reviewer should test authentication, authorization, tenant isolation, secrets, cryptography/key custody, input handling, SSRF/source adapters, dependency risk, deployment IAM, logging leakage, availability controls, and settlement-authorization integrity.
