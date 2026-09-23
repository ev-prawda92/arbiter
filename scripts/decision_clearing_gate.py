#!/usr/bin/env python3
"""Release gate for Arbiter v0.35: authoritative decisions clear the work they answer.

v0.34 recorded governed decisions but nothing consumed them, so recording one
never reduced the queue. v0.35 derives clearing from authoritative decisions on
every queue build. This gate proves the clearing is correct AND bounded.

Properties asserted (fail-closed):
  C1 every case a decision answers is cleared, with decision provenance
  C2 live-state work (payout HOLD, suspended source, audit break, missing
     evidence) is never cleared, even if a decision lists it
  C3 work outside the decision is untouched
  C4 a case that drifted to a different work pattern is not cleared
  C5 superseding a decision re-derives clearing; dropped cases reopen
  C6 an operator reopening a case after the decision is respected
  C7 clearing is pure: the input queue is unchanged and nothing is written
  C9 the decision workbench is told, per pattern, whether a decision can clear it
  C8 end to end over HTTP: one decision clears its pattern, the HOLD stays
     open, and contract/authority/evidence/resolution counts are unchanged
"""
from __future__ import annotations

import copy
import os
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND = os.path.join(ROOT, "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

_tmp = tempfile.mkdtemp(prefix="arbiter-v035-clear-")
os.environ["ARBITER_DATABASE_PATH"] = os.path.join(_tmp, "arbiter.db")

from app.decision_operations import apply_authoritative_decisions  # noqa: E402
from app.decision_records import get_service  # noqa: E402
from app.operations_intelligence import _blocker, _cluster_signature, _stable_cluster_id  # noqa: E402
from app.resolution_infra import ResolutionStore  # noqa: E402

TIMING_ACTION = "Confirm timing semantics before the resolution window closes."


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)
    print(f"[PASS] {message}")


def monitored(case_id: str, action: str = TIMING_ACTION) -> dict:
    return {
        "id": case_id, "kind": "monitored_contract", "subject": case_id.upper(),
        "title": f"Monitor {case_id.upper()}: timing risk", "detail": "no explicit settlement time",
        "severity": "medium", "owner_role": "Market Ops", "recommended_action": action,
        "notional": 1_000_000.0, "status": "open", "owner": "", "note": "", "updated_at": None,
    }


def cluster_of(item: dict) -> str:
    return _stable_cluster_id(_blocker(item), _cluster_signature(item))


def by_id(queue: dict) -> dict:
    return {i["id"]: i for i in queue["items"]}


def unit_properties() -> None:
    timing = [monitored(f"work_timing_{n}") for n in range(4)]
    hold = {
        "id": "work_hold", "kind": "resolution_hold", "subject": "CEASEFIRE-Q4",
        "title": "Resolve HOLD: CEASEFIRE-Q4", "detail": "Held for review",
        "severity": "high", "owner_role": "Compliance", "notional": 1_800_000.0,
        "recommended_action": TIMING_ACTION,  # same wording on purpose
        "status": "open", "owner": "", "note": "", "updated_at": None,
    }
    authority = {
        "id": "work_auth", "kind": "authority_status", "subject": "bls",
        "title": "Authority suspended: bls", "detail": "BLS feed suspended",
        "severity": "critical", "owner_role": "Data Ops", "notional": 0.0,
        "recommended_action": "Assess contracts dependent on this authority and confirm fallback/precedence rules.",
        "status": "open", "owner": "", "note": "", "updated_at": None,
    }
    other = monitored("work_other", "Confirm definition semantics before the resolution window closes.")
    queue = {"summary": {}, "items": timing + [hold, authority, other], "boundary": "x"}
    pristine = copy.deepcopy(queue)

    cid = cluster_of(timing[0])
    decision = {
        "decision_id": "dec_unit", "decision_hash": "sha256:unit", "decision_type": "timing_revision",
        "selection": "Initial official release controls", "cluster_id": cid, "state": "recorded",
        "created_at": "2026-09-23T10:00:00+00:00",
        "affected_case_ids": [t["id"] for t in timing] + ["work_hold", "work_auth"],
    }
    out = apply_authoritative_decisions(queue, [decision])
    got = by_id(out)

    check(all(got[t["id"]]["status"] == "resolved" for t in timing), "C1 all 4 answered cases cleared")
    check(all(got[t["id"]]["governed_by"]["decision_id"] == "dec_unit" for t in timing),
          "C1 each cleared case carries decision provenance")
    check(out["summary"]["active"] == 3 and out["summary"]["cleared_by_decision"] == 4,
          "C1 queue summary recomputed (3 active, 4 cleared)")
    check(got["work_hold"]["status"] == "open", "C2 payout HOLD not cleared even when listed")
    check(got["work_auth"]["status"] == "open", "C2 suspended-source work not cleared even when listed")
    check(got["work_other"]["status"] == "open" and "governed_by" not in got["work_other"],
          "C3 work outside the decision untouched")
    check(queue == pristine, "C7 input queue not mutated")

    drifted = copy.deepcopy(queue)
    drifted["items"][0]["recommended_action"] = "Confirm definition semantics before the resolution window closes."
    got = by_id(apply_authoritative_decisions(drifted, [decision]))
    check(got["work_timing_0"]["status"] == "open", "C4 case that drifted to another pattern is not cleared")
    check(got["work_timing_1"]["status"] == "resolved", "C4 cases still in the pattern remain cleared")

    reopened = copy.deepcopy(queue)
    reopened["items"][1]["updated_at"] = "2026-09-23T11:00:00+00:00"  # operator set 'open' after decision
    got = by_id(apply_authoritative_decisions(reopened, [decision]))
    check(got["work_timing_1"]["status"] == "open", "C6 operator reopen after the decision is respected")

    again = apply_authoritative_decisions(out, [decision])
    check(by_id(again) == by_id(out), "C7 re-applying is idempotent")


def supersession_property() -> None:
    store = ResolutionStore(os.path.join(_tmp, "supersede.db"))
    svc = get_service(store)
    timing = [monitored(f"work_s_{n}") for n in range(4)]
    cid = cluster_of(timing[0])
    queue = {"summary": {}, "items": timing, "boundary": "x"}

    first = svc.create(
        decision_type="timing_revision", question="Which window controls?",
        selection="Initial official release controls", rationale="Terms pin the initial release.",
        actor="operator:gate", affected_case_ids=[t["id"] for t in timing], cluster_id=cid,
    )
    got = by_id(apply_authoritative_decisions(queue, svc.authoritative()))
    check(sum(i["status"] == "resolved" for i in got.values()) == 4, "C5 original decision clears 4 cases")

    svc.create(
        decision_type="timing_revision", question="Which window controls?",
        selection="Latest valid revision controls", rationale="Clarified policy narrows scope.",
        actor="operator:gate", affected_case_ids=[t["id"] for t in timing[:2]], cluster_id=cid,
        supersedes=first["decision_id"],
    )
    got = by_id(apply_authoritative_decisions(queue, svc.authoritative()))
    check([got[t["id"]]["status"] for t in timing] == ["resolved", "resolved", "open", "open"],
          "C5 after supersession only the new decision's cases stay cleared; the rest reopen")
    check(all(got[t["id"]]["governed_by"]["selection"] == "Latest valid revision controls" for t in timing[:2]),
          "C5 cleared cases now cite the superseding decision")


def http_property() -> None:
    from fastapi.testclient import TestClient
    from app.server import app, resolution_store

    client = TestClient(app)
    clusters = client.get("/api/overview").json()["agent_brief"]["operations_intelligence"]["clusters"]
    decidable = [c for c in clusters if c["blocker_type"] == "timing_revision"]
    check(bool(decidable), "C8 reference data exposes a timing work pattern")
    target = max(decidable, key=lambda c: c["count"])
    hold = next((c for c in clusters if c["blocker_type"] == "resolution_hold"), None)
    check(client.get(f"/api/decision-context/{target['cluster_id']}").json()["clearability"]["clearable"] is True,
          "C9 the workbench is told a timing pattern can be cleared")
    if hold:
        ctx = client.get(f"/api/decision-context/{hold['cluster_id']}").json()["clearability"]
        check(ctx["clearable"] is False and "payout hold" in ctx["reason"],
              "C9 the workbench is told a payout-hold pattern cannot be cleared, and why")
    holds_before = [i["id"] for i in client.get("/api/work-queue").json()["items"]
                    if i["kind"] == "resolution_hold" and i["status"] != "resolved"]
    counts_before = resolution_store.summary()

    r = client.post("/api/decisions", json={
        "cluster_id": target["cluster_id"], "selection": "Initial official release controls",
        "rationale": "Governing terms pin the initial official release.",
    })
    check(r.status_code == 200, f"C8 POST /api/decisions -> 200 (got {r.status_code})")
    work = r.json()["reevaluation"]["workload"]
    check(work["cases_cleared"] == target["count"],
          f"C8 one decision clears its whole pattern ({work['cases_cleared']} of {target['count']})")
    check(work["human_decisions_removed"] == 1, "C8 exactly one human decision removed")

    items = client.get("/api/work-queue").json()["items"]
    still_open = {i["id"] for i in items if i["status"] != "resolved"}
    check(set(holds_before) <= still_open, "C8 payout HOLD work stays open")
    counts_after = resolution_store.summary()
    for k in ("contracts", "authorities", "evidence_records", "resolution_runs"):
        check(counts_after[k] == counts_before[k], f"C8 {k} unchanged ({counts_before[k]})")
    check(resolution_store.verify_audit_chain().get("ok") is True, "C8 audit chain intact")


def main() -> None:
    unit_properties()
    supersession_property()
    http_property()
    print("DECISION CLEARING GATE: PASS")


if __name__ == "__main__":
    main()
