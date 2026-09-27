#!/usr/bin/env python3
"""Gate for console access control (v0.45).

Properties asserted (fail-closed):

  K1  with no keys configured the server is open (local development, the demo)
      and says so: health reports auth "open"
  K2  with keys configured, health stays public and reports auth "keys"
  K3  every operational read needs a valid key: no key or a bad key is 401
  K4  reads need a read scope: a key with operations:read reads the queue,
      decisions, precedents and Ask; audit-only and unrelated keys get 403
  K5  an audit-only key still reads the audit trail and whoami
  K6  scopes still gate writes: a read-only key cannot record a decision
  K7  an admin key reads and writes everything it did before
  K8  the built console sends the key: the bundle carries the X-Arbiter-Key
      header, the per-tab key store and the sign-in screen
"""

from __future__ import annotations

import glob
import hashlib
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
KEYS = {"admin": "k-admin", "reader": "k-reader", "auditor": "k-auditor", "bench": "k-bench"}
RECORDS = [
    {"id": "admin", "scopes": ["admin:*"], "principal_id": "operator:admin"},
    {"id": "reader", "scopes": ["operations:read"], "principal_id": "operator:reader"},
    {"id": "auditor", "scopes": ["audit:read", "audit:export"], "principal_id": "auditor:acme-llp"},
    {"id": "bench", "scopes": ["benchmark:run"], "principal_id": "service:bench"},
]


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)
    print(f"[PASS] {message}")


def probe(mode: str) -> dict:
    """Run the requests in a fresh interpreter so env config is read cleanly."""
    tmp = tempfile.mkdtemp(prefix="arbiter-access-")
    env = dict(os.environ)
    env.pop("ARBITER_API_KEY_RECORDS", None)
    env.pop("ARBITER_API_KEYS", None)
    env.pop("ARBITER_DEMO_MODE", None)
    env.update({"ARBITER_DATABASE_PATH": os.path.join(tmp, "a.db"), "ARBITER_POLICY_PATH": os.path.join(tmp, "p.json")})
    if mode == "keys":
        env["ARBITER_API_KEY_RECORDS"] = json.dumps(
            [dict(r, sha256=hashlib.sha256(KEYS[r["id"]].encode()).hexdigest()) for r in RECORDS]
        )
    child = r"""
import json, sys
sys.path.insert(0, sys.argv[1])
from fastapi.testclient import TestClient
from app.server import app
c = TestClient(app)
keys = json.loads(sys.argv[2])
def h(who): return {"X-Arbiter-Key": keys[who]} if who else {}
out = {"health": c.get("/api/health").json()}
reads = ["/api/overview", "/api/work-queue", "/api/decisions", "/api/precedents"]
for who in [None, "bad", "admin", "reader", "auditor", "bench"]:
    hdr = {"X-Arbiter-Key": "nope"} if who == "bad" else h(who)
    tag = who or "none"
    out[tag] = {p: c.get(p, headers=hdr).status_code for p in reads}
    out[tag]["ask"] = c.post("/api/ask", json={"question": "who controls"}, headers=hdr).status_code
    out[tag]["audit"] = c.get("/api/audit/overview", headers=hdr).status_code
    out[tag]["whoami"] = c.get("/api/identity/whoami", headers=hdr).status_code
    out[tag]["decide"] = c.post("/api/decisions", json={"cluster_id": "cluster_missing", "selection": "s", "rationale": "r"}, headers=hdr).status_code
out["deny_detail"] = c.get("/api/overview", headers=h("auditor")).json().get("detail", "")
print(json.dumps(out))
"""
    res = subprocess.run(
        [sys.executable, "-c", child, os.path.join(ROOT, "backend"), json.dumps(KEYS)],
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    if res.returncode != 0:
        raise AssertionError(f"probe {mode} failed: {res.stderr[-2000:]}")
    return json.loads(res.stdout.strip().splitlines()[-1])


def main() -> int:
    reads = ["/api/overview", "/api/work-queue", "/api/decisions", "/api/precedents", "ask"]

    open_ = probe("open")
    check(open_["health"].get("auth") == "open", "K1 health reports auth 'open' when no keys are configured")
    check(all(open_["none"][p] == 200 for p in reads), "K1 local-open: reads work without a key")

    keys = probe("keys")
    check(keys["health"].get("auth") == "keys", "K2 health is public and reports auth 'keys'")
    check(all(keys["none"][p] == 401 for p in reads), "K3 no key: every operational read is 401")
    check(all(keys["bad"][p] == 401 for p in reads), "K3 a bad key: every operational read is 401")
    check(all(keys["reader"][p] == 200 for p in reads), "K4 operations:read reads queue, decisions, precedents and Ask")
    check(all(keys["auditor"][p] == 403 for p in reads), "K4 an audit-only key cannot read operational data")
    check(all(keys["bench"][p] == 403 for p in reads), "K4 an unrelated scope cannot read operational data")
    check("operations:read" in keys["deny_detail"], "K4 the refusal names the scope needed")
    check(
        keys["auditor"]["audit"] == 200 and keys["auditor"]["whoami"] == 200,
        "K5 an audit-only key still reads the audit trail and whoami",
    )
    check(keys["reader"]["audit"] == 403, "K5 operations:read alone does not open the audit trail")
    check(keys["reader"]["decide"] == 403, "K6 a read-only key cannot record a decision")
    check(
        all(keys["admin"][p] == 200 for p in reads) and keys["admin"]["audit"] == 200,
        "K7 an admin key reads everything",
    )
    check(keys["admin"]["decide"] in (404, 422), "K7 an admin key reaches the decision handler (unknown pattern)")

    bundles = glob.glob(os.path.join(ROOT, "backend", "dist", "assets", "*.js"))
    text = "".join(open(b, encoding="utf-8", errors="ignore").read() for b in bundles)
    check(bool(bundles), "K8 the console is built")
    check(
        "X-Arbiter-Key" in text and "arbiter.key" in text and "Sign in to Arbiter" in text,
        "K8 the console sends the key and has a sign-in screen",
    )
    print("ACCESS GATE: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
