# Arbiter v0.42: Auditor Workspace

Outside auditors can now run a whole engagement inside Arbiter: sample, test, record
findings and sign off. The exchange can see that an audit happened but can't edit it.

## Engagements (Audit → Engagements)

- **Open** an engagement for a period. It belongs to the auditor who opened it: only that
  auditor can change it, not the exchange's administrators and not another firm.
- **Sample** governed decisions, departures from precedent, or manual closes. The sample is
  reproducible: the seed comes from the engagement and the chain head at the moment of
  sampling, and items are ranked by `sha256(seed|id)`.
- **Test** each sampled item as no exception, exception (a note is required) or not
  testable. Arbiter attaches its mechanical checks as evidence:
  - the record's hash recomputes;
  - it is committed to the chain;
  - a rationale is recorded;
  - the precedent status is recorded;
  - any departure is distinguished or overruled.

  The conclusion stays the auditor's.
- **Findings** are linked to the items that raised them.
- **Keys:** the auditor generates an Ed25519 key on their own machine
  (`tools/arbiter-verify/sign.py keygen`) and registers only the public key when opening.
- **The sample is drawn once**, from a population defined on the audit chain up to a
  cutoff.
- **Sign off** requires every item tested and an opinion. Arbiter prepares the exact
  report, and the auditor signs its hash on their machine and pastes the signature. The
  server verifies it before locking. The signed report, `arbiter.audit-report.v1`,
  contains:
  - the period attestation: decisions, share following precedent when one applied,
    departures, overrules, manual closes, deciders;
  - the sample, the results and the findings;
  - the chain head it attests to, and the head of the working-paper log.

## Integrity

- **Working papers are their own hash chain.** Every engagement action is an append-only
  entry, and each entry's hash is also committed to Arbiter's main chain.
- **The evidence package now carries the engagement logs.** The standalone verifier checks
  both chains. With `--report`, it also checks a signed report:
  - the report's hash;
  - that the report is identical to its signed log entry;
  - that the chain head it attests to is in the package;
  - that the sample reproduces from the package alone.
- **The gate proves the verifier catches edits.** A report edited and re-hashed is
  rejected, and so are edited working papers.

## Independent review

A separate reviewer found nine defects before release, all fixed:
- **Nothing proved the auditor wrote their own work.** Whoever controlled the database
  could add or alter entries and commit them. Sign-off now needs the auditor's Ed25519
  signature. The server checks it with the `cryptography` library, and the verifier checks
  it with a small pure-Python RFC 8032 implementation, tested against the RFC's vector and
  that library.
- **A crash between writing an entry and committing it to the main chain broke every
  later package.** Both now happen in one transaction, and the export reads one snapshot.
- **The sample could be redrawn until it looked favourable.** It is now drawn once.
- **Only decision samples were reproduced, and the attestation never was.** The verifier
  now recomputes all three populations and the attestation.
- **Server and verifier defined populations differently.** Both now use one definition on
  chain events, with whole-date periods and a cutoff sequence.
- **Entries after sign-off were ignored.** They are now rejected.
- **Postgres could fork an engagement chain.** A unique `(engagement_id, previous_hash)`
  constraint now prevents it.
- **Callers with no identity fell back to a shared "auditor" name.** They now get a 401.
- **The spec claimed more than the verifier checked.** It is now aligned.

## Access

- `audit:engage` opens and works engagements. `audit:read` can view them.

## Validation

- **New `scripts/audit_engagement_gate.py`, 31 checks.** It covers:
  - ownership and scope rules;
  - sample reproduction;
  - testing rules;
  - findings;
  - sign-off rules and locking;
  - dual commitment of working papers;
  - verifier checks on reports, including tampering.
- The whole workflow was clicked through in the browser: the key generated and the report
  signed with the real tool, then the downloaded report verified against the downloaded
  package with the auditor's key.
- All 29 gates pass, and the release gate passes 452/452.
