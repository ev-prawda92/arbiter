# Arbiter audit evidence package: `arbiter.audit-package.v1`

This spec lets an outside auditor verify an Arbiter record without trusting Arbiter or
the exchange that runs it. The reference verifier is `tools/arbiter-verify/verify.py`. It
uses the Python standard library only, and anyone can reimplement it from this page.

## Canonical hash

`H(x) = "sha256:" + hex(SHA-256(json(x)))`

`json(x)` is JSON with keys sorted and separators `,` and `:` (no spaces). Values that are
not JSON types are written as strings.

## Files (zip)

| File | Contents |
|---|---|
| `manifest.json` | format, generator, product version, sequence and time range, chain `first_previous_hash` and `head_hash`, record counts, SHA-256 of every other file, `manifest_hash` |
| `events.jsonl` | every audit event, in sequence order |
| `contracts.jsonl` | every contract version (`spec_hash`) |
| `evidence.jsonl` | every evidence record (`record_hash`) |
| `decisions.jsonl` | every governed decision (`decision_hash`) |
| `precedents.jsonl` | every precedent (informational) |
| `anchors.jsonl` | anchor receipts recorded inside Arbiter (self-reported) |
| `engagements.jsonl` | auditor engagement logs: each entry `{engagement_id, at, actor, kind, payload, previous_hash, entry_hash}` |

## Rules a verifier checks

1. **Files:**
   - The zip holds exactly `manifest.json`, `README.txt` and the seven `.jsonl` files, with no
     extras and no duplicate names.
   - Each data file's SHA-256 matches `manifest.files`.
   - `manifest_hash` equals `H(manifest without manifest_hash)`.
2. **Events:** the package holds the whole chain, from genesis.
   - The first event has `sequence` 1 and `previous_hash` `null`, and
     `manifest.chain.first_previous_hash` is `null`.
   - Sequences are contiguous. Each `previous_hash` equals the prior `event_hash`.
   - Each `event_hash` equals `H({event_id, occurred_at, actor, action, object_type, object_id, details, previous_hash})`.
   - `range` and `chain.head_hash` match the events.
3. **Records:** each record is bound to the one event that committed it.

   | File | Hash field | Committing action | Event identifies the record by |
   |---|---|---|---|
   | contracts | `spec_hash` | `contract.version.created` | `object_id` = `contract_id`, `details.version` = `contract_version` |
   | evidence | `record_hash` | `evidence.appended` | `object_id` = `evidence_id` |
   | decisions | `decision_hash` | `decision.recorded` | `object_id` = `decision_id` |

   - Each record's hash field equals `H(record without that field)`.
   - It equals the hash in its committing event's `details`.
   - Every committing event has its record in the package, and no record appears twice.
4. **Anchor receipts** (`arbiter.audit-anchor.v1`):
   - Each receipt is also stored inside the chain, as the `details.receipt` of an
     `audit.anchored` event, written in one step.
   - `receipt_hash` equals `H(receipt without receipt_hash)`.
   - The package's event at `receipt.sequence` has `event_hash == receipt.event_hash`.

5. **Auditor engagements:**
   - Per engagement, each entry's `entry_hash` equals
     `H({engagement_id, at, actor, kind, payload, previous_hash})`, and each `previous_hash`
     equals the prior entry's hash.
   - The first entry is `opened`. There is at most one `sampled` entry, and nothing
     follows `signed`.
   - Each entry is committed to the main chain by an `audit.engagement.<kind>` event, with
     `object_id` set to the engagement and `details.entry_hash` set to the entry's hash. The
     entry and its commit are written in one transaction, and commit counts match.
6. **Signed report** (`arbiter.audit-report.v1`, checked with `--report` and
   `--auditor-key`):
   - `report_hash` equals `H(report without report_hash)`.
   - The report is identical to the `payload.report` of the engagement's `signed` entry.
   - `payload.signature` is a valid Ed25519 signature, by the auditor's public key, over
     `"arbiter-audit-report:" + report_hash`. The key must come from the auditor, not from
     the package. `report.auditor_public_key` must equal it.
   - `chain.event_hash` is the package's event at `chain.sequence`.
   - `attestation` recomputes from the events up to `chain.sequence` plus
     `decisions.jsonl` (the definitions are below).
   - The sample reproduces:
     - `seed = hex(SHA-256(engagement_id + "|" + seed_basis.chain_hash))`, where
       `seed_basis.chain_hash` is the event at `cutoff_sequence`;
     - the population is recomputed from the events up to `cutoff_sequence`, and its
       sorted-id hash equals `population_hash`;
     - the items are the first `size` of that population, ranked by
       `hex(SHA-256(seed + "|" + item_id))`.

### Populations and attestation

Periods are whole UTC dates, compared against the first 10 characters of an event's
`occurred_at`.

| Population | Events | Item id |
|---|---|---|
| `decisions` | `decision.recorded` | `object_id` (the decision id) |
| `departures` | `precedent.distinguished`, `precedent.overruled` | `event_id` |
| `manual_closes` | `work_item.updated` with `details.status == "resolved"` and an actor not starting `system:` | `event_id` |

The attestation fields are:
- `decisions`: size of the decisions population.
- `precedent_status`: counts of each decision's `metadata.precedent_consistency.status`,
  or `unrecorded`.
- `followed_when_precedent_applied`: (follows + consistent) / (follows + consistent +
  divergent), rounded to 3 places.
- `departures` and `overrules`: counts of those events in the period.
- `manual_closes`: size of that population.
- `deciders`: the sorted actors of `decision.recorded` events in the period.

## What each check proves

- **Rules 1–3:** no event or record was edited, removed, inserted, reordered or swapped
  for another, and nothing was cut from the start of the chain.
- **Rule 4:** needs a receipt the auditor obtained earlier and kept outside Arbiter. It
  proves the record up to that receipt was not regenerated wholesale since then. Without
  external receipts, a verifier proves internal consistency only, and it says so.

Anchor regularly (for example at each period close), and send each receipt to the auditor
when it is made.

## Scope and access

- **Access:**
  - `audit:read` reads the trail.
  - `audit:export` anchors and exports (both are POSTs, and both are recorded in the chain
    under the caller's identity).
  - `audit:engage` opens and works engagements. Only the principal that opened an
    engagement can change it, and signing needs the auditor's own key. So an exchange
    administrator can neither sign nor alter a signed report. Entries before sign-off are
    protected by the application, not by the signature; the auditor reviews them before
    signing, and the signature covers `engagement_log_head`. A signed engagement is locked.
  - Known limit: on Postgres, export runs at READ COMMITTED. Export from a quiesced replica.
  - None of these scopes can record decisions or change any record.
- **Tenancy:** a package contains the whole database it was exported from. Arbiter's
  reference deployment is one tenant per database. A multi-tenant deployment must export
  per tenant (not yet implemented).
