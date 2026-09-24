#!/usr/bin/env python3
"""Release gate for Arbiter v0.42: the auditor workspace.

E1 an auditor opens an engagement; only that auditor can change it (not the
   exchange's admin, not another auditor, not a read-only key)
E2 the sample is drawn by a published, reproducible method from the period's
   decisions, seeded from the chain head
E3 testing: only sampled items, exceptions need a note, Arbiter's mechanical
   checks are attached to each test
E4 findings are recorded against items
E5 sign-off needs every item tested and an opinion; it produces a report with
   the period attestation, and locks the engagement
E6 every engagement action is its own hash-chained entry, committed to the main
   chain (the exchange sees the audit happened; nobody can rewrite it)
E7 the standalone verifier checks the signed report against the evidence
   package: its hash, its log entry, the chain head it attests to, and that the
   sample reproduces; it rejects an edited report and edited working papers
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
import zipfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "backend"))
_tmp = tempfile.mkdtemp(prefix="arbiter-v042-engage-")
os.environ["ARBITER_DATABASE_PATH"] = os.path.join(_tmp, "arbiter.db")
os.environ.setdefault("ARBITER_POLICY_PATH", os.path.join(_tmp, "policy.json"))
KEYS = {
    "ops": (["admin:*"], "operator:gate"),
    "acme": (["audit:read", "audit:export", "audit:engage"], "auditor:acme-llp"),
    "other": (["audit:read", "audit:engage"], "auditor:other-firm"),
    "reader": (["audit:read"], "auditor:reader"),
}
os.environ["ARBITER_API_KEY_RECORDS"] = json.dumps(
    [
        {"id": k, "sha256": hashlib.sha256(k.encode()).hexdigest(), "scopes": s, "principal_id": p}
        for k, (s, p) in KEYS.items()
    ]
)

from fastapi.testclient import TestClient  # noqa: E402

from app import venue_intake as vi  # noqa: E402
from app.resolution_infra import canonical_hash  # noqa: E402
from app.server import app, resolution_store as store  # noqa: E402

VERIFY = os.path.join(ROOT, "tools", "arbiter-verify", "verify.py")
sys.path.insert(0, os.path.join(ROOT, "tools", "arbiter-verify"))
import ed25519  # noqa: E402

SECRET = hashlib.sha256(b"acme-llp-gate-key").digest()
PUB = ed25519.public_key(SECRET).hex()
WRONG = hashlib.sha256(b"someone-else").digest()


def sig(secret, report_hash):
    return ed25519.sign(secret, f"arbiter-audit-report:{report_hash}".encode()).hex()


def H(k):
    return {"X-Arbiter-Key": k}


def check(ok, msg):
    if not ok:
        raise AssertionError(msg)
    print(f"[PASS] {msg}")


def main() -> int:
    c = TestClient(app)
    with gzip.open(os.path.join(ROOT, "tests", "fixtures", "venue_scan_2026-09-24.json.gz"), "rt") as fh:
        pool = {"kalshi": [], "polymarket": []}
        for m in json.load(fh)["markets"]:
            pool[m["venue"]].append((m["raw"], m["url"]))
    ev, f, st = vi.discover(lambda v, limit: pool[v], limit=5000, store=store)
    vi.sync(store, ev, fetcher=f, boilerplate=st["boilerplate"])
    clusters = c.get("/api/overview", headers=H("ops")).json()["agent_brief"]["operations_intelligence"]["clusters"]
    decided = 0
    for cl in clusters:
        r = c.post(
            "/api/decisions",
            headers=H("ops"),
            json={
                "cluster_id": cl["cluster_id"],
                "selection": f"Ruling {decided}",
                "rationale": "Per the governing terms.",
            },
        )
        decided += r.status_code == 200
    check(decided >= 5, f"setup: {decided} governed decisions recorded")
    today = store.audit_log(limit=1)[0]["occurred_at"][:10]

    # E1
    r = c.post(
        "/api/audit/engagements",
        headers=H("acme"),
        json={
            "name": "Q3 resolution controls",
            "period_from": "2026-01-01",
            "period_to": today,
            "auditor_public_key": PUB,
        },
    )
    check(r.status_code == 200 and r.json()["auditor"] == "auditor:acme-llp", "E1 auditor opens an engagement")
    eid = r.json()["engagement_id"]
    check(
        c.post(
            "/api/audit/engagements",
            headers=H("reader"),
            json={"name": "x", "period_from": "2026-01-01", "period_to": today, "auditor_public_key": PUB},
        ).status_code
        == 403,
        "E1 a read-only key cannot open one",
    )
    for who in ("ops", "other"):
        rr = c.post(f"/api/audit/engagements/{eid}/sample", headers=H(who), json={"population": "decisions", "size": 3})
        check(rr.status_code == 403, f"E1 {KEYS[who][1]} cannot change another auditor's engagement ({rr.status_code})")
    check(
        c.get(f"/api/audit/engagements/{eid}", headers=H("reader")).status_code == 200,
        "E1 the engagement is visible to read-only access",
    )

    # E2
    size = 4
    s = c.post(
        f"/api/audit/engagements/{eid}/sample", headers=H("acme"), json={"population": "decisions", "size": size}
    ).json()
    smp = s["sample"]
    chain = [e for e in store.audit_log(limit=100000) if e["sequence"] <= smp["cutoff_sequence"]]
    pop_ids = sorted({e["object_id"] for e in chain if e["action"] == "decision.recorded"})
    expect = sorted(pop_ids, key=lambda i: hashlib.sha256(f"{smp['seed']}|{i}".encode()).hexdigest())[:size]
    check(
        smp["population_size"] == len(pop_ids) and [i["item_id"] for i in smp["items"]] == expect,
        "E2 sample = first n of the population (from the chain, up to the cutoff) ranked by sha256(seed|id)",
    )
    basis = smp["seed_basis"]
    check(
        smp["seed"] == hashlib.sha256(f"{eid}|{basis['chain_hash']}".encode()).hexdigest(),
        "E2 seed derives from the engagement and the chain head at the cutoff",
    )
    check(
        c.post(
            f"/api/audit/engagements/{eid}/sample", headers=H("acme"), json={"population": "decisions", "size": size}
        ).status_code
        == 422,
        "E2 the sample is drawn once: no redrawing until it looks favourable",
    )

    # E3
    items = [i["item_id"] for i in smp["items"]]
    check(
        c.post(
            f"/api/audit/engagements/{eid}/test",
            headers=H("acme"),
            json={"item_id": "dec_not_sampled", "result": "no_exception"},
        ).status_code
        == 422,
        "E3 only sampled items can be tested",
    )
    check(
        c.post(
            f"/api/audit/engagements/{eid}/test", headers=H("acme"), json={"item_id": items[0], "result": "exception"}
        ).status_code
        == 422,
        "E3 an exception needs a note",
    )
    check(
        c.post(f"/api/audit/engagements/{eid}/prepare", headers=H("acme"), json={"opinion": "x"}).status_code == 422,
        "E5 cannot prepare a report with untested items",
    )
    for n, i in enumerate(items):
        res = "exception" if n == 0 else "no_exception"
        s = c.post(
            f"/api/audit/engagements/{eid}/test",
            headers=H("acme"),
            json={"item_id": i, "result": res, "note": "Rationale cites no authority." if n == 0 else ""},
        ).json()
    t0 = s["tests"][items[0]]
    check(
        t0["result"] == "exception"
        and any(ch["check"] == "Committed to the audit chain" and ch["ok"] for ch in t0["checks"]),
        "E3 Arbiter's mechanical checks are attached to each test",
    )

    # E4
    s = c.post(
        f"/api/audit/engagements/{eid}/findings",
        headers=H("acme"),
        json={
            "title": "Rationales do not cite the governing source",
            "severity": "medium",
            "description": "1 of 4 sampled rulings.",
            "item_ids": [items[0]],
        },
    ).json()
    check(len(s["findings"]) == 1, "E4 finding recorded against the item")

    # E5 prepare, sign with the auditor's key
    opinion = "Controls operated effectively, except as noted."
    check(
        c.post(f"/api/audit/engagements/{eid}/prepare", headers=H("acme"), json={"opinion": ""}).status_code == 422,
        "E5 an opinion is required",
    )
    d1 = c.post(f"/api/audit/engagements/{eid}/prepare", headers=H("acme"), json={"opinion": opinion}).json()
    d2 = c.post(f"/api/audit/engagements/{eid}/prepare", headers=H("acme"), json={"opinion": opinion}).json()
    rh = d1["report"]["report_hash"]
    check(
        rh == d2["report"]["report_hash"] and d1["sign_message"] == f"arbiter-audit-report:{rh}",
        "E5 the draft report is deterministic, with an exact message to sign",
    )
    sign = lambda h, sg: c.post(
        f"/api/audit/engagements/{eid}/sign",
        headers=H("acme"),
        json={"opinion": opinion, "report_hash": h, "signature": sg},
    )  # noqa: E731
    check(sign(rh, sig(WRONG, rh)).status_code == 422, "E5 a signature from any other key is refused")
    check(
        sign("sha256:" + "0" * 64, sig(SECRET, "sha256:" + "0" * 64)).status_code == 422,
        "E5 signing a stale or different report hash is refused",
    )
    r = sign(rh, sig(SECRET, rh))
    s = r.json()
    rep = s["report"]
    check(
        r.status_code == 200 and s["state"] == "signed" and rep["results"] == {"exception": 1, "no_exception": 3},
        "E5 signed with the auditor's key; results summarized",
    )
    check(rep["attestation"]["decisions"] == len(pop_ids), "E5 report carries the period attestation")
    check(
        c.post(
            f"/api/audit/engagements/{eid}/test",
            headers=H("acme"),
            json={"item_id": items[1], "result": "exception", "note": "late"},
        ).status_code
        == 422,
        "E5 a signed engagement is locked",
    )

    # E6
    lg = c.get(f"/api/audit/engagements/{eid}/log", headers=H("reader")).json()
    main_ = [
        e for e in store.audit_log(limit=5000) if e["action"].startswith("audit.engagement.") and e["object_id"] == eid
    ]
    check(
        lg["verified"]["ok"] and len(main_) == len(lg["entries"]),
        f"E6 {len(lg['entries'])} engagement entries, each committed to the main chain",
    )
    from app.audit_engagement import get_engagements

    svc = get_engagements(store)
    orig = store.append_audit

    def boom(*a, **k):
        raise RuntimeError("crash between writes")

    store.append_audit = boom
    try:
        svc._append(eid, "auditor:acme-llp", "finding", {"x": 1})
    except RuntimeError:
        pass
    finally:
        store.append_audit = orig
    check(
        len(svc.log(eid)) == len(lg["entries"]),
        "E6 a crash before the main-chain commit leaves no orphan entry (one transaction)",
    )

    # second engagement: manual closes population, to prove non-decision samples reproduce
    queue = c.get("/api/work-queue", headers=H("ops")).json()["items"]
    for it in queue[:3]:
        c.post(
            f"/api/work-queue/{it['id']}",
            headers=H("ops"),
            json={"status": "resolved", "actor": "operator:jane", "note": "closing"},
        )
    e2 = c.post(
        "/api/audit/engagements",
        headers=H("acme"),
        json={"name": "Manual closes", "period_from": "2026-01-01", "period_to": today, "auditor_public_key": PUB},
    ).json()["engagement_id"]
    s2 = c.post(
        f"/api/audit/engagements/{e2}/sample", headers=H("acme"), json={"population": "manual_closes", "size": 2}
    ).json()
    for it in s2["sample"]["items"]:
        c.post(
            f"/api/audit/engagements/{e2}/test",
            headers=H("acme"),
            json={"item_id": it["item_id"], "result": "no_exception"},
        )
    d = c.post(
        f"/api/audit/engagements/{e2}/prepare", headers=H("acme"), json={"opinion": "Manual closes were documented."}
    ).json()["report"]
    rep2 = c.post(
        f"/api/audit/engagements/{e2}/sign",
        headers=H("acme"),
        json={
            "opinion": "Manual closes were documented.",
            "report_hash": d["report_hash"],
            "signature": sig(SECRET, d["report_hash"]),
        },
    ).json()["report"]
    check(
        s2["sample"]["population_size"] >= 3 and rep2["sample"]["population"] == "manual_closes",
        "E6 a second engagement samples manual closes",
    )

    # E7
    pkg = os.path.join(_tmp, "pkg.zip")
    open(pkg, "wb").write(c.post("/api/audit/package", headers=H("acme")).content)

    def run(report, *keys, package=pkg):
        rp = os.path.join(_tmp, "report.json")
        json.dump(report, open(rp, "w"))
        args = [sys.executable, VERIFY, package, "--report", rp]
        for k in keys:
            args += ["--auditor-key", k]
        return subprocess.run(args, capture_output=True, text=True)

    out = run(rep, PUB)
    check(
        out.returncode == 0
        and "signed with the auditor's key" in out.stdout
        and "sample reproduces" in out.stdout
        and "attestation recomputes" in out.stdout,
        f"E7 report verifies: signature, attestation, sample\n{out.stdout[-700:]}",
    )
    out = run(rep2, PUB)
    check(
        out.returncode == 0 and "manual_closes sample reproduces" in out.stdout,
        "E7 a manual-closes sample reproduces too",
    )
    out = run(rep)
    check(
        out.returncode == 1 and "supply the auditor's public key" in out.stdout,
        "E7 without the auditor's key the report is not accepted",
    )
    out = run(rep, ed25519.public_key(WRONG).hex())
    check(
        out.returncode == 1 and "made with a key you did not supply" in out.stdout,
        "E7 against a different key it fails",
    )
    bad = copy.deepcopy(rep)
    bad["opinion"] = "Controls operated effectively."
    bad["report_hash"] = canonical_hash({k: v for k, v in bad.items() if k != "report_hash"})
    check(run(bad, PUB).returncode == 1, "E7 an edited, re-hashed report is rejected")
    bad = copy.deepcopy(rep)
    bad["attestation"]["decisions"] += 1
    bad["report_hash"] = canonical_hash({k: v for k, v in bad.items() if k != "report_hash"})
    out = run(bad, PUB)
    check(out.returncode == 1 and "FAIL] report" in out.stdout, "E7 a report with inflated statistics is rejected")

    with zipfile.ZipFile(pkg) as z:
        files = {n: z.read(n) for n in z.namelist()}

    def forged(log, name):
        fs = dict(files)
        fs["engagements.jsonl"] = "".join(json.dumps(x, sort_keys=True) + "\n" for x in log).encode()
        m = json.loads(fs["manifest.json"])
        m["files"]["engagements.jsonl"] = "sha256:" + hashlib.sha256(fs["engagements.jsonl"]).hexdigest()
        m.pop("manifest_hash")
        m["manifest_hash"] = canonical_hash(m)
        fs["manifest.json"] = json.dumps(m).encode()
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            for n, b in fs.items():
                z.writestr(n, b)
        path = os.path.join(_tmp, name)
        open(path, "wb").write(buf.getvalue())
        return subprocess.run([sys.executable, VERIFY, path], capture_output=True, text=True)

    log = [json.loads(x) for x in files["engagements.jsonl"].decode().splitlines()]
    edited = copy.deepcopy(log)
    next(x for x in edited if x["kind"] == "tested")["payload"]["result"] = "no_exception"
    out = forged(edited, "edited.zip")
    check(out.returncode == 1 and "breaks" in out.stdout, "E7 edited working papers are rejected")
    extra = copy.deepcopy(log)
    last = [x for x in extra if x["engagement_id"] == eid][-1]
    after = {
        "engagement_id": eid,
        "at": last["at"],
        "actor": last["actor"],
        "kind": "finding",
        "payload": {"title": "added later"},
        "previous_hash": last["entry_hash"],
    }
    after["entry_hash"] = canonical_hash(after)
    extra.insert(extra.index(last) + 1, after)
    out = forged(extra, "after.zip")
    check(
        out.returncode == 1 and ("after sign-off" in out.stdout or "not committed" in out.stdout),
        "E7 an entry appended after sign-off is rejected",
    )
    print("AUDIT ENGAGEMENT GATE: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
