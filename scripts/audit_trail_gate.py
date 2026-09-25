#!/usr/bin/env python3
"""Release gate for Arbiter v0.41: the audit trail, for auditors.

A1  concurrent writers never fork the chain (320 events from 8 threads verify)
A2  lineage of a contract holds exactly its own steps, in order, from intake to
    decision, with the ruling and the precedent departure
A3  the audit log searches by text, stage and actor
A4  exceptions surface a departure from precedent and a case closed by hand
    without a governed decision; decided cases are not flagged
A5  an anchor receipt is recorded in the chain and hashes to itself
A6  an exported package verifies with the standalone verifier (clean, with receipt)
A7  the verifier catches: an edited event, a deleted event, an edited decision,
    a decision swapped for one the chain never committed to, a tampered file
A8  a chain rebuilt wholesale with every hash recomputed passes internal checks
    but fails against the auditor's receipt
A9  an auditor key (audit:read only) reads everything, cannot record decisions,
    and its export is recorded under its own identity; no key gets nothing
A10 reading the trail (overview, log, lineage, exceptions) writes nothing
"""

from __future__ import annotations

import copy
import gzip
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import zipfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "backend"))
_tmp = tempfile.mkdtemp(prefix="arbiter-v041-audit-")
os.environ["ARBITER_DATABASE_PATH"] = os.path.join(_tmp, "arbiter.db")
os.environ.setdefault("ARBITER_POLICY_PATH", os.path.join(_tmp, "policy.json"))
ADMIN, AUDITOR, READER = "gate-admin-key", "gate-auditor-key", "gate-reader-key"
os.environ["ARBITER_API_KEY_RECORDS"] = json.dumps(
    [
        {
            "id": "ops",
            "sha256": hashlib.sha256(ADMIN.encode()).hexdigest(),
            "scopes": ["admin:*"],
            "principal_id": "operator:gate",
        },
        {
            "id": "acme",
            "sha256": hashlib.sha256(AUDITOR.encode()).hexdigest(),
            "scopes": ["audit:read", "audit:export"],
            "principal_id": "auditor:acme-llp",
        },
        {
            "id": "reader",
            "sha256": hashlib.sha256(READER.encode()).hexdigest(),
            "scopes": ["audit:read"],
            "principal_id": "auditor:reader",
        },
    ]
)

from fastapi.testclient import TestClient  # noqa: E402

from app import venue_intake as vi  # noqa: E402
from app.resolution_infra import ResolutionStore, canonical_hash  # noqa: E402
from app.server import app, resolution_store as store  # noqa: E402

VERIFY = os.path.join(ROOT, "tools", "arbiter-verify", "verify.py")
A = {"X-Arbiter-Key": ADMIN}
AUD = {"X-Arbiter-Key": AUDITOR}


def check(ok: bool, msg: str) -> None:
    if not ok:
        raise AssertionError(msg)
    print(f"[PASS] {msg}")


def verify(path: str, *receipts: str) -> subprocess.CompletedProcess:
    args = [sys.executable, VERIFY, path]
    for r in receipts:
        args += ["--anchor", r]
    return subprocess.run(args, capture_output=True, text=True)


def rezip(files: dict[str, bytes], name: str) -> str:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for n, b in files.items():
            z.writestr(n, b)
    path = os.path.join(_tmp, name)
    open(path, "wb").write(buf.getvalue())
    return path


def jsonl(rows) -> bytes:
    return "".join(json.dumps(r, sort_keys=True) + "\n" for r in rows).encode()


def reseal(files: dict[str, bytes], **chain) -> dict[str, bytes]:
    """What a forger with full access would do: fix every file hash and the manifest."""
    m = json.loads(files["manifest.json"])
    m["files"] = {n: "sha256:" + hashlib.sha256(b).hexdigest() for n, b in files.items() if n.endswith(".jsonl")}
    m["chain"].update(chain)
    m.pop("manifest_hash")
    m["manifest_hash"] = canonical_hash(m)
    return {**files, "manifest.json": json.dumps(m).encode()}


def main() -> int:
    # A1
    side = ResolutionStore(os.path.join(_tmp, "concurrency.db"))

    def writer(n):
        for i in range(40):
            side._audit(f"t{n}", "test.event", "x", f"{n}-{i}", {"i": i})

    threads = [threading.Thread(target=writer, args=(n,)) for n in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    res = side.verify_audit_chain()
    check(res["ok"] and res["events"] == 320, f"A1 8 concurrent writers, 320 events, chain verifies ({res})")

    client = TestClient(app)
    with gzip.open(os.path.join(ROOT, "tests", "fixtures", "venue_scan_2026-09-24.json.gz"), "rt") as fh:
        pool = {"kalshi": [], "polymarket": []}
        for m in json.load(fh)["markets"]:
            pool[m["venue"]].append((m["raw"], m["url"]))

    def ingest(p):
        ev, f, st = vi.discover(lambda v, limit: p.get(v, []), limit=5000, store=store)
        return vi.sync(store, ev, fetcher=f, boilerplate=st["boilerplate"])

    ingest(pool)
    clusters = client.get("/api/overview", headers=A).json()["agent_brief"]["operations_intelligence"]["clusters"]
    g7 = next(c for c in clusters if c["count"] == 7)
    ruling = "Death in office counts as leaving office; resolve on the date the office is vacated"
    r = client.post(
        "/api/decisions",
        headers=A,
        json={"cluster_id": g7["cluster_id"], "selection": ruling, "rationale": "Vacancy date controls."},
    )
    check(r.status_code == 200, "setup: G7 ruling recorded")
    nxt = []
    for raw, url in pool["kalshi"]:
        if str(raw.get("event_ticker", "")).startswith("KXG7LEADEROUT"):
            x = copy.deepcopy(raw)
            x["event_ticker"] = x["event_ticker"].replace("26JUL20", "27JAN20")
            x["ticker"] = x["ticker"].replace("26JUL20", "27JAN20")
            nxt.append((x, url + "#next"))
    ingest({"kalshi": nxt})
    pattern = next(
        c
        for c in client.get("/api/overview", headers=A).json()["agent_brief"]["operations_intelligence"]["clusters"]
        if c["count"] == 7
    )
    r = client.post(
        "/api/decisions",
        headers=A,
        json={
            "cluster_id": pattern["cluster_id"],
            "selection": "Only resignation or removal counts",
            "rationale": "New terms.",
            "distinguish": "The Jan 2027 terms exclude death.",
        },
    )
    check(r.status_code == 200, "setup: a departure from precedent recorded with a distinction")
    queue = client.get("/api/work-queue", headers=A).json()["items"]
    manual = next(i for i in queue if "Chinese Communist" in i["title"] and i["status"] != "resolved")
    client.post(
        f"/api/work-queue/{manual['id']}",
        headers=A,
        json={"status": "resolved", "actor": "operator:jane", "note": "closing"},
    )

    # A2 lineage
    cid = "kalshi:KXG7LEADEROUT-27JAN20-DJT"
    lin = client.get(f"/api/audit/lineage/{cid}", headers=AUD).json()
    acts = [e["action"] for e in lin["events"]]
    order = [
        "contract.version.created",
        "precedent.matched",
        "evidence.exception.opened",
        "decision.recorded",
        "precedent.distinguished",
    ]
    pos = [acts.index(a) if a in acts else -1 for a in order]
    check(
        all(p >= 0 for p in pos) and pos == sorted(pos),
        f"A2 lineage runs intake -> match -> flag -> decision -> departure ({acts})",
    )
    others = [
        e
        for e in lin["events"]
        if e["object_type"] in ("contract", "work_item")
        and e["object_id"] not in (cid, *[c["work_item_id"] for c in lin["cases"]])
    ]
    check(not others, f"A2 no sibling contract's or case's events leak in ({len(others)})")
    g = lin["governing_decision"]
    check(
        g
        and g["selection"] == "Only resignation or removal counts"
        and g["precedent_consistency"]["status"] == "divergent",
        "A2 governing ruling and its departure are shown",
    )
    check(
        lin["lineage_hash"] == canonical_hash([e["event_hash"] for e in lin["events"]]),
        "A2 lineage fingerprint recomputes",
    )

    # A3 search
    log = client.get("/api/audit/log?q=distinguished", headers=AUD).json()
    check(
        log["total"] >= 1 and all("distinguish" in (e["action"] + json.dumps(e["details"])) for e in log["events"]),
        "A3 text search",
    )
    st = client.get("/api/audit/log?stage=decision", headers=AUD).json()
    check(st["total"] >= 3 and all(e["stage"] == "decision" for e in st["events"]), "A3 stage filter")
    act = client.get("/api/audit/log?actor=operator:jane", headers=AUD).json()
    check(act["total"] == 1 and act["events"][0]["action"] == "work_item.updated", "A3 actor filter")

    # A4 exceptions
    exc = client.get("/api/audit/exceptions", headers=AUD).json()
    kinds = exc["counts"]
    check(kinds.get("departure") == 1, f"A4 the departure from precedent is flagged ({kinds})")
    check(
        kinds.get("manual_close") == 1 and any(manual["id"] in i["title"] for i in exc["items"]),
        "A4 the case closed by hand without a decision is flagged",
    )
    check(kinds.get("unanchored") == 1, "A4 a never-anchored chain is flagged")

    # A5 anchor
    before_head = client.get("/api/audit/overview", headers=AUD).json()["head_sequence"]
    receipt = client.post("/api/audit/anchor", headers=AUD, json={"note": "gate"}).json()
    check(
        receipt["sequence"] == before_head
        and canonical_hash({k: v for k, v in receipt.items() if k != "receipt_hash"}) == receipt["receipt_hash"],
        "A5 receipt names the head and hashes to itself",
    )
    check(
        client.get("/api/audit/log?action=audit.anchored", headers=AUD).json()["events"][0]["actor"]
        == "auditor:acme-llp",
        "A5 anchoring is recorded under the auditor's identity",
    )
    rpath = os.path.join(_tmp, "receipt.json")
    json.dump(receipt, open(rpath, "w"))

    # A6 export + verify
    resp = client.post("/api/audit/package", headers=AUD)
    check(resp.status_code == 200 and resp.headers["content-type"] == "application/zip", "A6 package downloads")
    pkg = os.path.join(_tmp, "pkg.zip")
    open(pkg, "wb").write(resp.content)
    out = verify(pkg, rpath)
    check(
        out.returncode == 0 and "VERIFIED" in out.stdout,
        f"A6 clean package verifies with the receipt\n{out.stdout[-400:]}",
    )
    check("external receipt" in out.stdout, "A6 the verifier checked the external receipt")
    with zipfile.ZipFile(pkg) as z:
        files = {n: z.read(n) for n in z.namelist()}
    events = [json.loads(line) for line in files["events.jsonl"].decode().splitlines()]
    decisions = [json.loads(line) for line in files["decisions.jsonl"].decode().splitlines()]

    # A7 tampering
    def expect_fail(name, fs, needle):
        o = verify(rezip(fs, name))
        check(o.returncode == 1 and needle in o.stdout, f"A7 caught: {name} ({needle})")

    ev = copy.deepcopy(events)
    ev[10]["actor"] = "someone-else"
    expect_fail("edited-event", reseal({**files, "events.jsonl": jsonl(ev)}), "was altered")
    ev = copy.deepcopy(events)
    del ev[20]
    expect_fail("deleted-event", reseal({**files, "events.jsonl": jsonl(ev)}), "sequence gap")
    dc = copy.deepcopy(decisions)
    dc[0]["selection"] = "Something else"
    expect_fail("edited-decision", reseal({**files, "decisions.jsonl": jsonl(dc)}), "altered")
    dc = copy.deepcopy(decisions)
    dc[0]["selection"] = "Something else"
    dc[0]["decision_hash"] = canonical_hash({k: v for k, v in dc[0].items() if k != "decision_hash"})
    expect_fail("swapped-decision", reseal({**files, "decisions.jsonl": jsonl(dc)}), "do not")
    expect_fail(
        "tampered-file", {**files, "evidence.jsonl": files["evidence.jsonl"] + b"{}\n"}, "FAIL] file evidence.jsonl"
    )

    # A7b forgeries found by the independent review
    k = 25
    cut = copy.deepcopy(events[k:])
    dropped = {e["object_id"] for e in events[:k]}
    fs = {**files, "events.jsonl": jsonl(cut)}
    for fname, idf in (
        ("contracts.jsonl", "contract_id"),
        ("evidence.jsonl", "evidence_id"),
        ("decisions.jsonl", "decision_id"),
    ):
        keep = [json.loads(x) for x in files[fname].decode().splitlines() if json.loads(x).get(idf) not in dropped]
        fs[fname] = jsonl(keep)
    expect_fail(
        "truncated-front",
        reseal(fs, first_previous_hash=events[k]["previous_hash"]),
        "does not start at the first event",
    )
    dc = copy.deepcopy(decisions)[1:]
    expect_fail("deleted-decision", reseal({**files, "decisions.jsonl": jsonl(dc)}), "committed but absent")
    ev_recs = [json.loads(x) for x in files["evidence.jsonl"].decode().splitlines()]
    a0, a1 = ev_recs[0], ev_recs[1]
    swapped = [dict(a1, evidence_id=a0["evidence_id"])] + ev_recs[1:]
    swapped[0]["record_hash"] = canonical_hash({k2: v for k2, v in swapped[0].items() if k2 != "record_hash"})
    expect_fail("evidence-swapped-under-another-id", reseal({**files, "evidence.jsonl": jsonl(swapped)}), "do not")
    expect_fail("extra-file", {**files, "notes.txt": b"hi"}, "exact file set")
    fs = dict(files)
    fs.pop("decisions.jsonl")
    expect_fail("missing-file", fs, "exact file set")

    # A8 wholesale rewrite
    prev = json.loads(files["manifest.json"])["chain"]["first_previous_hash"]
    rewritten = []
    for e in copy.deepcopy(events):
        if e["action"] == "decision.recorded":
            e["actor"] = "operator:someone-else"
        e["previous_hash"] = prev
        body = {
            k: e[k]
            for k in (
                "event_id",
                "occurred_at",
                "actor",
                "action",
                "object_type",
                "object_id",
                "details",
                "previous_hash",
            )
        }
        e["event_hash"] = canonical_hash(body)
        prev = e["event_hash"]
        rewritten.append(e)
    forged = reseal({**files, "events.jsonl": jsonl(rewritten), "anchors.jsonl": b""}, head_hash=prev)
    fpath = rezip(forged, "rewritten.zip")
    check(verify(fpath).returncode == 0, "A8 a wholesale rewrite passes internal checks alone (why receipts matter)")
    o = verify(fpath, rpath)
    check(
        o.returncode == 1 and "rewritten since this receipt" in o.stdout, "A8 the auditor's receipt exposes the rewrite"
    )

    # A9 auditor role
    check(client.get("/api/audit/overview").status_code == 401, "A9 no key: no access")
    r = client.post(
        "/api/decisions", headers=AUD, json={"cluster_id": pattern["cluster_id"], "selection": "x", "rationale": "y"}
    )
    check(r.status_code == 403, f"A9 auditor key cannot record decisions ({r.status_code})")
    exported = client.get("/api/audit/log?action=audit.exported", headers=AUD).json()["events"]
    check(
        exported and exported[0]["actor"] == "auditor:acme-llp",
        "A9 the export is recorded under the auditor's identity",
    )

    R = {"X-Arbiter-Key": READER}
    check(client.get("/api/audit/overview", headers=R).status_code == 200, "A9 a read-only auditor can read")
    check(
        client.post("/api/audit/anchor", headers=R, json={}).status_code == 403, "A9 a read-only auditor cannot anchor"
    )
    check(client.post("/api/audit/package", headers=R).status_code == 403, "A9 a read-only auditor cannot export")
    n_exp = client.get("/api/audit/log?action=audit.exported", headers=AUD).json()["total"]
    g = client.get("/api/audit/package", headers=AUD)
    check(
        g.headers.get("content-type") != "application/zip"
        and client.get("/api/audit/log?action=audit.exported", headers=AUD).json()["total"] == n_exp,
        "A9 a GET never exports (no side effects from links or prefetch)",
    )

    # A10 reads write nothing
    with store.connect() as db:
        n0 = db.execute("SELECT COUNT(*) n FROM audit_events").fetchone()["n"]
    for path in (
        "/api/audit/overview",
        "/api/audit/log?q=x",
        f"/api/audit/lineage/{cid}",
        "/api/audit/exceptions",
        "/api/audit/anchors",
        "/api/audit/contracts",
    ):
        check(client.get(path, headers=AUD).status_code == 200, f"A10 GET {path}")
    with store.connect() as db:
        n1 = db.execute("SELECT COUNT(*) n FROM audit_events").fetchone()["n"]
    check(n0 == n1, "A10 reading the trail writes nothing")
    check(store.verify_audit_chain()["ok"], "A10 chain verifies at the end")
    print("AUDIT TRAIL GATE: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
