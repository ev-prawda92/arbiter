# Security Policy

Arbiter is pre-production resolution infrastructure. Security reports are welcome and should be handled privately.

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting / Security Advisory workflow for this repository when available. Do not disclose suspected vulnerabilities in a public issue, discussion, pull request, or social post before they are reviewed.

Include, when possible:

- affected component and version or commit;
- reproduction steps or proof of concept;
- expected vs. observed behavior;
- security impact;
- suggested mitigation, if known.

## Scope

Especially important areas include:

- authentication, authorization, tenant isolation, and API keys;
- evidence or contract tampering;
- audit-chain integrity;
- idempotency and replay behavior;
- settlement / authorization boundaries;
- secrets handling;
- unsafe model-to-control-plane privilege escalation;
- benchmark label leakage or holdout compromise.

## Current status

Arbiter is not represented as independently security-certified, production settlement authority, or regulatory-approved infrastructure. Internal validation and passing release gates do not replace external security review, penetration testing, deployment hardening, or operational assurance.

## Disclosure

Please allow reasonable time to investigate and remediate a report before public disclosure. Coordinated disclosure is preferred.
