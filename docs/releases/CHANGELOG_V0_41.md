# Arbiter v0.41: Audit Trail for Auditors

Arbiter's hash-chained record is now something an exchange's compliance team and an outside
auditor can use directly, and can verify without trusting Arbiter.

## New: Audit section

- **Lineage:** everything that happened to one contract, in order, each step tied to its
  audit event. It runs through intake, the flag, the case, the governing ruling and its
  precedent status (followed, distinguished or overruled), appeals, resolution runs,
  approvals and settlement. A lineage fingerprint (the hash of its event hashes) can be
  cited in workpapers.
- **Audit log:** every event in plain language, searchable by text, stage and actor.
- **Exceptions:** what an auditor should look at first:
  - departures from precedent, with the stated reason
  - overrules and superseded decisions
  - reopened cases
  - cases closed by hand without a governed decision
  - cases closed by re-triage
  - self-approval, and the same person deciding and approving settlement
  - a chain that is unanchored or broken
- **Evidence package:** anchor the chain and export `arbiter.audit-package.v1`.

## Independent verification

- **`tools/arbiter-verify/verify.py`:** standard library only, run on the auditor's own
  machine. The format is published in `docs/audit/PACKAGE_SPEC.md`, so anyone can
  reimplement it.
- **What it checks:**
  - an exact file set
  - the whole chain from genesis
  - every event hash
  - every contract version, evidence record and decision, each bound to the one event
    that committed it, both ways
  - anchor receipts
- **Anchor receipts:** a hash chain proves no single event was edited. It can't prove the
  chain wasn't rebuilt from scratch. A receipt the auditor keeps outside Arbiter does: the
  gate rebuilds a chain with every hash recomputed, shows it passes internal checks alone,
  and shows the receipt exposes it.

## Access

- `audit:read` reads everything and can change nothing.
- `audit:export` anchors and exports. Both are POSTs, and both are recorded in the chain
  under the auditor's identity.
- Reading the trail writes nothing.

## Fixes found along the way

- **Chain forks under concurrent writes.** Eight writers at once produced 13 forks, and
  the chain then failed verification with no tampering. Appends now take a write lock
  (SQLite `BEGIN IMMEDIATE`, Postgres advisory lock). The gate proves 320 concurrent
  events verify.
- **401 surfaced as a 500.** With API keys configured outside production, a request
  without a key crashed as a 500 instead of a 401. It now returns 401.

## Independent review

A separate reviewer read the change before release and found nine defects, all fixed.
The most serious: deleting the start of the chain passed verification, even with
receipts. The verifier now requires the chain from genesis. The other fixes:
- records are bound to their committing event rather than to any event;
- the file set must be exact, with duplicate zip entries rejected;
- anchoring and export need a separate scope, and export is a POST;
- anchors are written atomically, inside the chain;
- lineage matches ids exactly and covers every decision;
- chain verification is cached;
- malformed packages fail cleanly instead of crashing.

The gate covers each forgery the reviewer described.

## Validation

- **New `scripts/audit_trail_gate.py`, 43 checks.** It covers concurrency, lineage, search,
  exceptions and anchoring, plus ten forgeries: edited, deleted and swapped records, a
  truncated front, missing and extra files, and a wholesale rewrite caught by the receipt.
  It also covers the auditor roles and that reads write nothing.
- All 28 gates pass, and the release gate passes 452/452.
