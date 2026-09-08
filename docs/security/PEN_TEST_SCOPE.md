# Penetration Test Scope — v0.26

## In scope
- public HTTPS API and frontend
- OIDC and API-key authentication
- tenant override and RLS boundary
- model-provider credential management
- evidence ingestion and external-source adapters
- settlement approval/authorization endpoints
- signed webhooks and replay controls
- shadow-pilot and reference-exchange endpoints
- object storage access paths
- deployment IAM roles and network boundaries

## Required classes
OWASP API Top 10, auth/session attacks, IDOR/BOLA, privilege escalation, injection, SSRF, replay, race/idempotency abuse, tenant breakout, secret leakage, malformed evidence, settlement double-execution attempts, and denial-of-service/backpressure behavior.

## Rules
Use a dedicated staging environment and synthetic/play-money data. No production venue settlement, real money, or customer secrets. Findings must include severity, reproduction, affected version/commit, remediation, and retest status.
