# Arbiter v0.45: Console Access Control

Arbiter can now run with authentication switched on and still be used through the console. Keys follow least privilege for reads as well as writes.

## What was missing

- **The console could not send a key.** Whenever API keys were configured, every console call returned 401, so a firm could not run the console with authentication on.
- **Reads had no scopes.** Every `/api/` request already needed a valid key once keys were configured. But any valid key, including an audit-only one, could read the whole live queue, every decision and every precedent.

## What changed

- **Sign-in.** When `/api/health` reports `"auth": "keys"`, the console asks for an API key:
  - the key is kept in `sessionStorage` for that browser tab only;
  - it is sent as `X-Arbiter-Key` on same-origin `/api/` requests, including the legacy views;
  - a 401 brings the sign-in screen back, and **Sign out** clears the key.
- **Read scopes.** Reading operational data needs `operations:read`, `operations:write` or `admin:*`. That covers `GET /api/*` outside `/api/audit`, plus the query-only POSTs `/api/ask`, `/api/decisions/consistency` and `/api/decision-precedents`.
  - Audit keys keep reading the audit trail under their `audit:*` scopes. An auditor who should also see the live queue is granted `operations:read` explicitly.
  - A refused read returns 403 and names the scope needed.
- **Open mode is visible.** `/api/health` reports `"auth": "open"` or `"keys"`, so it is obvious when a server runs without credentials, as local development and the read-only demo do. Production settings (`ARBITER_ENV=production`) already refuse to start without authentication.
- **No false "verified" badge.** The sidebar no longer says "Audit chain verified" before the chain has been checked.

## Upgrading

A key record that relied on implicit read access now needs `operations:read`. Records with `operations:write` or `admin:*` are unaffected. Audit-only keys (`audit:read`, `audit:export`, `audit:engage`) lose access to the live queue unless you add `operations:read`.

## Gate

`scripts/access_gate.py` (K1–K8) checks:
- open mode;
- the 401s for a missing or bad key;
- scope-based 403s for audit-only and unrelated keys;
- that audit keys still read the audit trail;
- that a read-only key cannot write;
- that admin keys still read and write;
- that the built console carries the key header and sign-in screen.
