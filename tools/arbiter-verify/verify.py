#!/usr/bin/env python3
"""Independent verifier for Arbiter audit evidence packages (arbiter.audit-package.v1).

Standard library only. Runs on the auditor's machine, against the auditor's copy,
without Arbiter installed. Read it: it is short on purpose.

    python3 verify.py arbiter-audit-package.zip
    python3 verify.py arbiter-audit-package.zip --anchor receipt.json [--anchor older.json]
    python3 verify.py package.zip --json

Checks
  1. every file matches the hash in the manifest, and the manifest matches its own hash
  2. every event's hash recomputes, and each event links to the one before it
  3. contracts, evidence and decisions recompute to their stored hashes, and each is
     committed to by an event in the chain (so a record cannot be swapped silently)
  4. anchors: each external receipt you hold names an event that is in the chain with
     the same hash. This is what shows the chain was not regenerated after the fact.
     A hash chain alone proves no single event was edited; only a receipt kept
     outside the exchange proves the whole chain was not rebuilt.

Exit code 0 when everything verifies, 1 otherwise.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import zipfile

FORMAT = "arbiter.audit-package.v1"
ANCHOR_FORMAT = "arbiter.audit-anchor.v1"


def canonical_hash(value) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def without(d: dict, key: str) -> dict:
    return {k: v for k, v in d.items() if k != key}


class Report:
    def __init__(self):
        self.checks: list[dict] = []
        self.engagement_log: list[dict] = []
        self.decisions: list[dict] = []
        self.events: list[dict] = []

    def add(self, ok: bool, name: str, detail: str = "") -> bool:
        self.checks.append({"ok": bool(ok), "check": name, "detail": detail})
        return ok

    @property
    def ok(self) -> bool:
        return all(c["ok"] for c in self.checks)


REQUIRED_FILES = {
    "manifest.json",
    "events.jsonl",
    "contracts.jsonl",
    "evidence.jsonl",
    "decisions.jsonl",
    "precedents.jsonl",
    "anchors.jsonl",
    "engagements.jsonl",
    "README.txt",
}
REPORT_FORMAT = "arbiter.audit-report.v1"
SIGNATURE_PREFIX = "arbiter-audit-report:"
EVENT_FIELDS = ("event_id", "occurred_at", "actor", "action", "object_type", "object_id", "details", "previous_hash")
# record file -> (hash field, committing action, how the event names the record)
BINDINGS = {
    "contracts.jsonl": (
        "spec_hash",
        "contract.version.created",
        lambda x: (x.get("contract_id"), x.get("contract_version")),
    ),
    "evidence.jsonl": ("record_hash", "evidence.appended", lambda x: (x.get("evidence_id"), None)),
    "decisions.jsonl": ("decision_hash", "decision.recorded", lambda x: (x.get("decision_id"), None)),
}


def event_key(action: str, e: dict):
    d = e.get("details") or {}
    return (e.get("object_id"), d.get("version") if action == "contract.version.created" else None)


def load(path: str, r: Report) -> tuple[dict, dict[str, bytes]] | None:
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        dupes = sorted({n for n in names if names.count(n) > 1})
        files = {n: z.read(n) for n in names}
    extra = sorted(set(files) - REQUIRED_FILES)
    missing = sorted(REQUIRED_FILES - set(files))
    r.add(not dupes, "no duplicate files", ", ".join(dupes))
    r.add(not extra and not missing, "exact file set", f"missing {missing} extra {extra}" if (extra or missing) else "")
    if "manifest.json" not in files:
        return None
    return json.loads(files["manifest.json"]), files


def rows(blob: bytes) -> list[dict]:
    return [json.loads(line) for line in blob.decode().splitlines() if line.strip()]


def verify(path: str, anchors: list[dict]) -> Report:
    r = Report()
    try:
        loaded = load(path, r)
    except (zipfile.BadZipFile, ValueError) as exc:
        r.add(False, "readable package", str(exc))
        return r
    if not loaded:
        return r
    manifest, files = loaded
    try:
        _verify(r, manifest, files, anchors)
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        r.add(False, "well-formed package", f"{type(exc).__name__}: {exc}")
    return r


def _verify(r: Report, manifest: dict, files: dict[str, bytes], anchors: list[dict]) -> None:
    r.add(manifest.get("format") == FORMAT, "package format", str(manifest.get("format")))
    r.add(canonical_hash(without(manifest, "manifest_hash")) == manifest.get("manifest_hash"), "manifest hash")

    # 1 files: every data file is listed and matches
    listed = manifest.get("files") or {}
    for name in sorted(REQUIRED_FILES - {"manifest.json", "README.txt"}):
        blob = files.get(name)
        got = "sha256:" + hashlib.sha256(blob).hexdigest() if blob is not None else None
        r.add(
            got is not None and got == listed.get(name),
            f"file {name}",
            "missing or not listed" if got is None or name not in listed else "",
        )

    events = rows(files.get("events.jsonl", b""))
    r.add(bool(events), "package has events")
    # 2 chain: must start at the genesis event, so nothing can be cut off the front
    prev, seq, bad = None, 0, None
    if manifest.get("chain", {}).get("first_previous_hash") is not None or (events and events[0]["sequence"] != 1):
        bad = "the package does not start at the first event of the chain (sequence 1, no previous hash)"
    for e in [] if bad else events:
        if e["sequence"] != seq + 1:
            bad = f"sequence gap after {seq} (next is {e['sequence']})"
            break
        if e["previous_hash"] != prev:
            bad = f"event {e['sequence']} does not link to the event before it"
            break
        if canonical_hash({k: e[k] for k in EVENT_FIELDS}) != e["event_hash"]:
            bad = f"event {e['sequence']} ({e['action']}) was altered: its hash does not recompute"
            break
        prev, seq = e["event_hash"], e["sequence"]
    r.add(bad is None, f"hash chain ({len(events)} events, from genesis)", bad or "")
    if events:
        r.add(events[-1]["event_hash"] == manifest.get("chain", {}).get("head_hash"), "chain head matches manifest")
        rng = manifest.get("range") or {}
        r.add(
            rng.get("from_sequence") == 1 and rng.get("to_sequence") == events[-1]["sequence"], "range matches events"
        )

    # 3 records: each bound to the event that committed it, both ways
    for fname, (field, action, key) in BINDINGS.items():
        recs = rows(files.get(fname, b""))
        label = fname.split(".")[0]
        altered = [x for x in recs if canonical_hash(without(x, field)) != x.get(field)]
        r.add(not altered, f"{label}: {len(recs)} recompute", f"{len(altered)} altered" if altered else "")
        commits = {}
        for e in events:
            if e["action"] == action:
                commits[event_key(action, e)] = (e.get("details") or {}).get(field)
        by_key = {key(x): x.get(field) for x in recs}
        unbound = [k for k, h in by_key.items() if commits.get(k) != h]
        absent = [k for k in commits if k not in by_key]
        r.add(
            not unbound,
            f"{label}: each matches the event that committed it",
            f"{len(unbound)} do not, e.g. {unbound[:1]}" if unbound else "",
        )
        r.add(
            not absent and len(by_key) == len(recs),
            f"{label}: none missing or duplicated",
            f"{len(absent)} committed but absent" if absent else "",
        )

    # 5 auditor engagements: each log is its own chain, every entry is committed to the
    # main chain, at most one sample, and nothing after sign-off
    log = rows(files.get("engagements.jsonl", b""))
    committed_entries = {
        (e.get("object_id"), (e.get("details") or {}).get("entry_hash"))
        for e in events
        if str(e.get("action", "")).startswith("audit.engagement.")
    }
    heads: dict = {}
    kinds: dict = {}
    bad_log = None
    for x in log:
        eid = x["engagement_id"]
        body = {k: x[k] for k in ("engagement_id", "at", "actor", "kind", "payload", "previous_hash")}
        seen = kinds.setdefault(eid, [])
        if x["previous_hash"] != heads.get(eid) or canonical_hash(body) != x["entry_hash"]:
            bad_log = f"engagement {eid} log breaks at a {x['kind']} entry"
        elif (eid, x["entry_hash"]) not in committed_entries:
            bad_log = f"engagement {eid} {x['kind']} entry is not committed to the main chain"
        elif "signed" in seen:
            bad_log = f"engagement {eid} has a {x['kind']} entry after sign-off"
        elif x["kind"] == "sampled" and "sampled" in seen:
            bad_log = f"engagement {eid} drew its sample more than once"
        elif (x["kind"] == "opened") != (not seen):
            bad_log = f"engagement {eid} does not start with its opening entry"
        if bad_log:
            break
        seen.append(x["kind"])
        heads[eid] = x["entry_hash"]
    n_committed = sum(1 for e in events if str(e.get("action", "")).startswith("audit.engagement."))
    r.add(
        bad_log is None and n_committed == len(log),
        f"auditor engagement logs ({len(log)} entries, {len(heads)} engagements)",
        bad_log or ("" if n_committed == len(log) else "main chain commits entries missing from the package"),
    )
    r.engagement_log = log
    r.decisions = rows(files.get("decisions.jsonl", b""))
    r.events = events

    # 4 anchors
    by_seq = {e["sequence"]: e["event_hash"] for e in events}
    for a in rows(files.get("anchors.jsonl", b"")):
        r.add(
            by_seq.get(a.get("sequence")) == a.get("event_hash"),
            f"internal anchor at {a.get('sequence')}",
            "self-reported by the package",
        )
    for a in anchors:
        if a.get("format") != ANCHOR_FORMAT or canonical_hash(without(a, "receipt_hash")) != a.get("receipt_hash"):
            r.add(False, f"receipt {a.get('anchor_id')}", "receipt itself is malformed or altered")
            continue
        got = by_seq.get(a["sequence"])
        r.add(
            got == a["event_hash"],
            f"external receipt {a['anchor_id']} (sequence {a['sequence']}, {a['anchored_at'][:19]})",
            ""
            if got == a["event_hash"]
            else ("event missing from package" if got is None else "chain was rewritten since this receipt"),
        )
    if not anchors:
        r.add(
            True,
            "external receipts",
            "none supplied: this run proves internal consistency only, not that the chain was never rebuilt",
        )


# ---- population and attestation: identical to backend/app/audit_engagement.py ----


def in_period(ts: str, period_from: str, period_to: str) -> bool:
    return period_from <= (ts or "")[:10] <= period_to


def population_from_events(kind: str, events: list, period_from: str, period_to: str) -> list:
    out = []
    for e in events:
        if not in_period(e["occurred_at"], period_from, period_to):
            continue
        a, d = e["action"], e.get("details") or {}
        if kind == "decisions" and a == "decision.recorded":
            out.append(e["object_id"])
        elif kind == "departures" and a in ("precedent.distinguished", "precedent.overruled"):
            out.append(e["event_id"])
        elif (
            kind == "manual_closes"
            and a == "work_item.updated"
            and d.get("status") == "resolved"
            and not str(e["actor"]).startswith("system:")
        ):
            out.append(e["event_id"])
    return out


def attestation_from(events: list, decisions: dict, period_from: str, period_to: str) -> dict:
    ids = population_from_events("decisions", events, period_from, period_to)
    statuses: dict = {}
    for i in ids:
        st = (((decisions.get(i) or {}).get("metadata") or {}).get("precedent_consistency") or {}).get(
            "status"
        ) or "unrecorded"
        statuses[st] = statuses.get(st, 0) + 1
    applied = sum(statuses.get(k, 0) for k in ("follows", "consistent", "divergent"))
    followed = statuses.get("follows", 0) + statuses.get("consistent", 0)
    period = [e for e in events if in_period(e["occurred_at"], period_from, period_to)]
    return {
        "decisions": len(ids),
        "precedent_status": dict(sorted(statuses.items())),
        "followed_when_precedent_applied": round(followed / applied, 3) if applied else None,
        "departures": sum(1 for e in period if e["action"] == "precedent.distinguished"),
        "overrules": sum(1 for e in period if e["action"] == "precedent.overruled"),
        "manual_closes": len(population_from_events("manual_closes", events, period_from, period_to)),
        "deciders": sorted({e["actor"] for e in period if e["action"] == "decision.recorded"}),
    }


def verify_report(r: Report, report: dict, auditor_keys: list) -> None:
    """A signed audit report, checked against the package and the auditor's own key."""
    import ed25519

    name = f"report {report.get('engagement_id')}"
    by_seq = {e["sequence"]: e for e in r.events}
    r.add(
        report.get("format") == REPORT_FORMAT
        and canonical_hash(without(report, "report_hash")) == report.get("report_hash"),
        f"{name}: hash recomputes",
    )
    signed = [
        x for x in r.engagement_log if x["kind"] == "signed" and x["engagement_id"] == report.get("engagement_id")
    ]
    entry = signed[-1]["payload"] if signed else {}
    r.add(entry.get("report") == report, f"{name}: identical to the signed entry in the engagement log")
    key = report.get("auditor_public_key") or ""
    if not auditor_keys:
        r.add(
            False,
            f"{name}: auditor signature",
            "supply the auditor's public key with --auditor-key (from the auditor, not from the package)",
        )
    else:
        ok = key in auditor_keys and ed25519.verify(
            bytes.fromhex(key),
            f"{SIGNATURE_PREFIX}{report.get('report_hash')}".encode(),
            bytes.fromhex(entry.get("signature") or "00"),
        )
        r.add(
            ok,
            f"{name}: signed with the auditor's key",
            "" if ok else "the signature is missing, invalid, or made with a key you did not supply",
        )
    ch = report.get("chain") or {}
    head = by_seq.get(ch.get("sequence"))
    r.add(
        bool(head) and head["event_hash"] == ch.get("event_hash"),
        f"{name}: attests to a chain head that is in this package",
    )
    upto = [e for e in r.events if e["sequence"] <= (ch.get("sequence") or 0)]
    decisions = {d.get("decision_id"): d for d in r.decisions}
    period = report.get("period") or {}
    r.add(
        attestation_from(upto, decisions, period.get("from"), period.get("to")) == report.get("attestation"),
        f"{name}: period attestation recomputes",
    )
    sample = report.get("sample") or {}
    basis = sample.get("seed_basis") or {}
    cut = by_seq.get(sample.get("cutoff_sequence"))
    r.add(
        basis.get("engagement_id") == report.get("engagement_id")
        and bool(cut)
        and cut["event_hash"] == basis.get("chain_hash")
        and sample.get("seed")
        == hashlib.sha256(f"{report.get('engagement_id')}|{basis.get('chain_hash') or ''}".encode()).hexdigest(),
        f"{name}: sample seed derives from this engagement and the chain at the cutoff",
    )
    pop = population_from_events(
        sample.get("population"),
        [e for e in r.events if e["sequence"] <= (sample.get("cutoff_sequence") or 0)],
        period.get("from"),
        period.get("to"),
    )
    ranked = sorted(pop, key=lambda i: hashlib.sha256(f"{sample.get('seed')}|{i}".encode()).hexdigest())[
        : sample.get("size", 0)
    ]
    r.add(
        canonical_hash(sorted(pop)) == sample.get("population_hash") and ranked == sample.get("item_ids"),
        f"{name}: {sample.get('population')} sample reproduces ({len(ranked)} of {len(pop)})",
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("package")
    ap.add_argument("--anchor", action="append", default=[], help="an anchor receipt you hold (JSON file)")
    ap.add_argument(
        "--report", action="append", default=[], help="a signed audit report (JSON) to check against the package"
    )
    ap.add_argument(
        "--auditor-key",
        action="append",
        default=[],
        help="the auditor's Ed25519 public key (hex), obtained from the auditor",
    )
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    receipts = [json.load(open(p)) for p in args.anchor]
    rep = verify(args.package, receipts)
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    for p in args.report:
        verify_report(rep, json.load(open(p)), [k.strip().lower() for k in args.auditor_key])
    if args.json:
        print(json.dumps({"ok": rep.ok, "checks": rep.checks}, indent=2))
    else:
        for c in rep.checks:
            print(f"[{'PASS' if c['ok'] else 'FAIL'}] {c['check']}" + (f" - {c['detail']}" if c["detail"] else ""))
        print("\nVERIFIED" if rep.ok else "\nNOT VERIFIED")
    return 0 if rep.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
