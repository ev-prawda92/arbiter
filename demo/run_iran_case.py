#!/usr/bin/env python3
"""Run the US-Iran nuclear deal case end to end through the Arbiter v0.35 engine.

What is real:
  * Market questions, criteria and final outcomes: captured from the Polymarket
    gamma-api (521878) and Kalshi elections-api (KXUSAIRANAGREEMENT-27-26SEP)
    on 2026-09-22. The 26AUG market's outcome was not re-fetched and is not claimed.
  * Everything else is produced by the engine in this run: the work queue
    (workflow.build_work_queue), work patterns and human-decision counts
    (operations_intelligence.analyze_queue), the governed decision record, its
    application, clearing (decision_operations.apply_authoritative_decisions),
    IDs, hashes and the hash-chained audit log.

What is a replay:
  * The queue is rebuilt as it stood when the MOU landed (June 2026): the two
    Kalshi series markets open on the same interpretive question, the Polymarket
    market already settled (Jan 1 2026), and two unrelated benchmark-seed markets.
    Timestamps are from this run, not from June.

What is a what-if (clearly labelled, run on a copy of the store):
  * A later ruling reversing the MOU interpretation, to show supersession:
    authority moves to the new ruling, the old one is refused, both stay audited.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "backend"))

from app import operations_intelligence, workflow  # noqa: E402
from app.decision_operations import (  # noqa: E402
    apply_authoritative_decisions,
    apply_decision_to_workflow,
    build_decision_prompt,
)
from app.decision_records import DecisionRecordService  # noqa: E402
from app.resolution_infra import (  # noqa: E402
    Authority,
    EvidenceRecord,
    ResolutionSpecification,
    ResolutionStore,
    canonical_hash,
    gen_id,
    utcnow,
)

OUT = os.path.join(os.path.dirname(__file__), "iran_case_run.json")
ACTOR = "operator:resolution-ops"

PM = {
    "venue": "polymarket",
    "market_id": "521878",
    "question": "US-Iran nuclear deal in 2025?",
    "outcome": "NO",
    "resolved_at": "2026-01-01T08:35:00Z",
    "criteria": "Official agreement publicly announced, mutual between US and Iran; official "
    "announcements plus consensus of credible reporting; window Feb 4 - Dec 31 2025.",
}
KS = {
    "venue": "kalshi",
    "market_id": "KXUSAIRANAGREEMENT-27-26SEP",
    "question": "Will the US agree to a new Iranian nuclear deal this year?",
    "outcome": "NO",
    "resolved_at": "2026-09-01T14:00:00Z",
    "criteria": "Formal written instrument with verifiable restrictions on enrichment/centrifuges "
    "AND sanctions lift or modification.",
}

MOU_ACTION = "Record whether the June 2026 US-Iran MOU satisfies the formal-agreement criterion."


def exception(subject: str, title: str, detail: str, action: str, kind: str, severity: str = "high") -> dict:
    """An operator exception in the shape workflow.build_work_queue ingests."""
    return {
        "kind": kind,
        "subject": subject,
        "title": title,
        "detail": detail,
        "severity": severity,
        "recommended_action": action,
    }


def build_queue(store: ResolutionStore) -> dict:
    """The June 2026 queue, built by the real work-queue builder."""
    infra = {
        "authorities": [],  # all approved: no authority-status work
        "audit_chain": {"ok": True},
        "evidence_exceptions": [
            exception(
                "KXUSAIRANAGREEMENT-27-26SEP",
                "Interpretive: does the June MOU count as a deal? (Kalshi 26SEP)",
                "Kalshi requires a formal written instrument with verifiable restrictions and sanctions relief.",
                MOU_ACTION,
                "policy_review",
            ),
            exception(
                "KXUSAIRANAGREEMENT-27-26AUG",
                "Interpretive: does the June MOU count as a deal? (Kalshi 26AUG)",
                "Kalshi requires a formal written instrument with verifiable restrictions and sanctions relief.",
                MOU_ACTION,
                "policy_review",
            ),
            exception(
                "POLYMARKET-521878",
                "Interpretive: does the June MOU count as a deal? (Polymarket 521878)",
                "Window closed Dec 31 2025; market settled NO on Jan 1 2026.",
                MOU_ACTION,
                "policy_review",
            ),
            exception(
                "POLYMARKET-527838",
                "Which CPI print controls? (March 2025, Polymarket 527838)",
                "Initial BLS release vs later revision.",
                "Confirm whether the initial or revised CPI release controls.",
                "timing_revision",
                "medium",
            ),
            exception(
                "POLYMARKET-546814",
                "Interpretive: does the outfit count as a suit? (Polymarket 546814)",
                "Disputed through five UMA rounds.",
                "Record whether the outfit worn qualifies as a suit under the market rules.",
                "policy_review",
                "medium",
            ),
        ],
    }
    return workflow.build_work_queue([], {}, infra, store.list_work_states())


def clone_db(src_path: str) -> str:
    """Consistent copy of a live SQLite store (includes not-yet-checkpointed writes)."""
    dst_path = os.path.join(tempfile.mkdtemp(prefix="arbiter-copy-"), "arbiter.db")
    src, dst = sqlite3.connect(src_path), sqlite3.connect(dst_path)
    with dst:
        src.backup(dst)
    src.close()
    dst.close()
    return dst_path


def workload(queue: dict) -> dict:
    s = operations_intelligence.analyze_queue(queue)["summary"]
    return {
        "active_cases": s["active_cases"],
        "human_decisions": s["estimated_human_decisions"],
        "work_patterns": s["distinct_work_patterns"],
    }


def compact(queue: dict) -> list[dict]:
    return [
        {
            "id": i["id"],
            "subject": i["subject"],
            "status": i["status"],
            "note": i.get("note") or "",
            "governed_by": i.get("governed_by"),
        }
        for i in queue["items"]
    ]


def main() -> None:
    tmp = tempfile.mkdtemp(prefix="arbiter-iran-v035-")
    db_path = os.path.join(tmp, "arbiter.db")
    store = ResolutionStore(db_path)
    svc = DecisionRecordService(store)

    # --- intake: authorities, contracts, evidence (as in the v0.34 run) ---
    for aid, name, org, kind in [
        ("auth_polymarket_rules", "Polymarket market rules", "Polymarket", "rules"),
        ("auth_kalshi_rules", "Kalshi contract terms", "Kalshi", "rules"),
        ("auth_official_statements", "US/Iran official statements", "US State Dept / Iran MFA", "official_statement"),
    ]:
        store.save_authority(
            Authority(authority_id=aid, version=1, name=name, organization=org, source_type=kind), actor="system:intake"
        )
    contracts = {}
    for m, auth in [(PM, "auth_polymarket_rules"), (KS, "auth_kalshi_rules")]:
        cid = f"{m['venue']}:{m['market_id']}"
        store.save_contract(
            ResolutionSpecification(
                contract_id=cid,
                contract_version=1,
                title=m["question"],
                definition={"yes_if": m["criteria"]},
                timing={"resolved_at": m["resolved_at"]},
                authority_ids=[auth, "auth_official_statements"],
                source_precedence=[auth, "auth_official_statements"],
                metadata={"venue": m["venue"], "cluster": "iran-nuclear-deal"},
            ),
            actor="system:intake",
            status="active",
        )
        contracts[m["venue"]] = cid

    def evidence(authority_id: str, contract_id: str, value: dict, locator: str, observed: str) -> dict:
        rec = EvidenceRecord(
            evidence_id=gen_id("evid"),
            authority_id=authority_id,
            authority_version=1,
            observed_at=observed,
            retrieved_at=utcnow(),
            normalized_value=value,
            raw_payload_hash=canonical_hash(value),
            parser_version="demo-0.2",
            contract_id=contract_id,
            source_locator=locator,
        )
        return store.append_evidence(rec, actor="system:evidence")

    e_mou = evidence(
        "auth_official_statements",
        contracts["kalshi"],
        {
            "event": "US-Iran Memorandum of Understanding",
            "date": "2026-06",
            "publicly_announced": True,
            "enrichment_limits": False,
            "centrifuge_caps": False,
            "sanctions_modification": False,
            "substance": "maintains status quo; defers commitments to future negotiations",
        },
        "public record, June 2026",
        "2026-06-30T00:00:00Z",
    )
    e_pm = evidence(
        "auth_polymarket_rules",
        contracts["polymarket"],
        {"final_outcome": PM["outcome"], "resolved_at": PM["resolved_at"]},
        "gamma-api.polymarket.com/markets/521878",
        PM["resolved_at"],
    )
    e_ks = evidence(
        "auth_kalshi_rules",
        contracts["kalshi"],
        {
            "final_outcome": KS["outcome"],
            "resolved_at": KS["resolved_at"],
            "venue_note": "June MOU ruled non-qualifying",
        },
        "api.elections.kalshi.com/trade-api/v2/markets/KXUSAIRANAGREEMENT-27-26SEP",
        KS["resolved_at"],
    )

    # --- June 2026 queue: Polymarket already settled ---
    pm_item = next(i for i in build_queue(store)["items"] if i["subject"] == "POLYMARKET-521878")
    store.set_work_state(
        pm_item["id"],
        "resolved",
        "Resolution Ops",
        "Settled NO on 2026-01-01; window closed before the MOU.",
        "system:venue-sync",
    )
    queue_before = build_queue(store)
    before = workload(queue_before)
    ops = operations_intelligence.analyze_queue(queue_before)
    ks_sep_id = next(i["id"] for i in queue_before["items"] if i["subject"] == KS["market_id"])
    cluster = next(c for c in ops["clusters"] if ks_sep_id in c["case_ids"])
    prompt = build_decision_prompt(cluster)
    counts_before = store.summary()

    # --- the one human decision (same path as POST /api/decisions) ---
    decision = svc.create(
        decision_type=prompt["decision_type"],
        question="Does the June 2026 US-Iran MOU constitute a qualifying nuclear agreement?",
        selection="MOU is non-qualifying",
        rationale=(
            "The MOU maintained the status quo and deferred substantive commitments to future "
            "negotiations. It contains no verifiable enrichment limits, centrifuge caps, or sanctions "
            "modification, so it does not meet the formal-instrument threshold."
        ),
        actor=ACTOR,
        affected_case_ids=list(cluster["case_ids"]),
        cluster_id=cluster["cluster_id"],
        contract_id=contracts["kalshi"],
        governing_rule="YES requires a formal written instrument with verifiable nuclear restrictions AND sanctions relief.",
        controlling_authority_ids=["auth_kalshi_rules", "auth_official_statements"],
        controlling_evidence_ids=[e_mou["evidence_id"]],
        policy_basis={"class": "interpretive_criteria"},
    )
    application = apply_decision_to_workflow(
        resolution_store=store, decision=decision, current_queue=queue_before, actor=ACTOR
    )

    # --- re-evaluation: rebuild the queue; authoritative decisions clear what they answer ---
    queue_after = apply_authoritative_decisions(build_queue(store), svc.authoritative(limit=500))
    after = workload(queue_after)
    counts_after = store.summary()
    chain = store.verify_audit_chain()
    audit = list(reversed(store.audit_log(limit=1000)))

    # --- tamper test on a copy ---
    tamper_path = clone_db(db_path)
    con = sqlite3.connect(tamper_path)
    con.execute(
        "UPDATE audit_events SET details_json=? WHERE action='decision.recorded'",
        (json.dumps({"selection": "MOU is qualifying"}),),
    )
    con.commit()
    con.close()
    tamper = ResolutionStore(tamper_path).verify_audit_chain()
    tamper_event = next(e["sequence"] for e in audit if e["action"] == "decision.recorded")

    # --- what-if (copy of the store): a later ruling reverses the interpretation ---
    wstore = ResolutionStore(clone_db(db_path))
    wsvc = DecisionRecordService(wstore)
    reversal = wsvc.create(
        decision_type=prompt["decision_type"],
        question="Does the June 2026 US-Iran MOU constitute a qualifying nuclear agreement?",
        selection="MOU is qualifying (hypothetical reversal)",
        rationale="WHAT-IF ONLY: a later clarification treats the signed MOU text as the formal instrument.",
        actor=ACTOR,
        affected_case_ids=list(cluster["case_ids"]),
        cluster_id=cluster["cluster_id"],
        contract_id=contracts["kalshi"],
        supersedes=decision["decision_id"],
        metadata={"what_if": True},
    )
    authoritative_ids = [d["decision_id"] for d in wsvc.authoritative(limit=500)]
    try:
        apply_decision_to_workflow(
            resolution_store=wstore, decision=decision, current_queue=build_queue(wstore), actor=ACTOR
        )
        old_refused = False
    except ValueError:
        old_refused = True
    wqueue = apply_authoritative_decisions(build_queue(wstore), wsvc.authoritative(limit=500))
    whatif = {
        "reversal_decision_id": reversal["decision_id"],
        "reversal_hash": reversal["decision_hash"],
        "supersedes": decision["decision_id"],
        "authoritative_ids": authoritative_ids,
        "original_is_authoritative": decision["decision_id"] in authoritative_ids,
        "original_refused_at_apply": old_refused,
        "records_kept": len(wsvc.list(limit=500)),
        "cases_now_cite": sorted(
            {(i.get("governed_by") or {}).get("decision_id") for i in wqueue["items"] if i.get("governed_by")}
        ),
        "audit_ok": wstore.verify_audit_chain(),
    }

    cleared = [
        i for i in queue_after["items"] if (i.get("governed_by") or {}).get("decision_id") == decision["decision_id"]
    ]
    result = {
        "engine": "arbiter v0.35.0",
        "run_at": utcnow(),
        "markets": {"polymarket": PM, "kalshi": KS},
        "contracts": contracts,
        "evidence": [
            {
                "evidence_id": e["evidence_id"],
                "authority_id": e["authority_id"],
                "source_locator": e["source_locator"],
                "record_hash": e["record_hash"],
                "value": e["normalized_value"],
            }
            for e in (e_mou, e_pm, e_ks)
        ],
        "queue_before": compact(queue_before),
        "work_patterns_before": [
            {
                "cluster_id": c["cluster_id"],
                "blocker_type": c["blocker_type"],
                "count": c["count"],
                "case_ids": c["case_ids"],
            }
            for c in ops["clusters"]
        ],
        "iran_pattern": {
            "cluster_id": cluster["cluster_id"],
            "blocker_type": cluster["blocker_type"],
            "case_ids": cluster["case_ids"],
            "question": prompt["question"],
        },
        "decision": decision,
        "application": application,
        "queue_after": compact(queue_after),
        "workload": {
            "before": before,
            "after": after,
            "cases_cleared": before["active_cases"] - after["active_cases"],
            "human_decisions_removed": before["human_decisions"] - after["human_decisions"],
        },
        "cleared": [{"id": i["id"], "subject": i["subject"], "note": i["note"]} for i in cleared],
        "counts_before": counts_before,
        "counts_after": counts_after,
        "audit": audit,
        "chain": chain,
        "tamper_test": {**tamper, "edited_event": tamper_event},
        "what_if": whatif,
    }
    with open(OUT, "w") as f:
        json.dump(result, f, indent=2, default=str)

    print(
        json.dumps(
            {
                "decision_id": decision["decision_id"],
                "iran_pattern_cases": [i["subject"] for i in queue_before["items"] if i["id"] in cluster["case_ids"]],
                "workload": result["workload"],
                "cleared": [c["subject"] for c in result["cleared"]],
                "still_open": [i["subject"] for i in queue_after["items"] if i["status"] != "resolved"],
                "semantic_counts_unchanged": all(
                    counts_before[k] == counts_after[k]
                    for k in ("contracts", "authorities", "evidence_records", "resolution_runs")
                ),
                "chain": chain,
                "tamper": result["tamper_test"],
                "what_if": {
                    k: whatif[k]
                    for k in (
                        "original_is_authoritative",
                        "original_refused_at_apply",
                        "records_kept",
                        "cases_now_cite",
                    )
                },
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
