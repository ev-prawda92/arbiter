#!/usr/bin/env python3
"""Run the Iran nuclear deal case through the real Arbiter v0.34 engine.

Market facts are the values captured live from Polymarket gamma-api (521878) and
Kalshi elections-api (KXUSAIRANAGREEMENT-27-26SEP) on 2026-09-22. Everything else --
IDs, hashes, audit chain, propagation result -- is produced by the engine in this run.
"""
from __future__ import annotations
import json, os, shutil, sqlite3, sys, tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "backend"))

from app.resolution_infra import (ResolutionStore, ResolutionSpecification, Authority,
                                  EvidenceRecord, canonical_hash, gen_id, utcnow)
from app.decision_records import get_service
from app.decision_operations import apply_decision_to_workflow

OUT = os.path.join(os.path.dirname(__file__), "iran_case_run.json")

PM = {"venue": "polymarket", "market_id": "521878", "question": "US-Iran nuclear deal in 2025?",
      "outcome": "NO", "resolved_at": "2026-01-01T08:35:00Z",
      "criteria": "Official agreement publicly announced, mutual between US and Iran; official announcements plus consensus of credible reporting; window Feb 4 - Dec 31 2025."}
KS = {"venue": "kalshi", "market_id": "KXUSAIRANAGREEMENT-27-26SEP",
      "question": "Will the US agree to a new Iranian nuclear deal this year?",
      "outcome": "NO", "resolved_at": "2026-09-01T14:00:00Z",
      "criteria": "Formal written instrument with verifiable restrictions on enrichment/centrifuges AND sanctions lift or modification."}

def main():
    tmp = tempfile.mkdtemp(prefix="arbiter-iran-")
    db_path = os.path.join(tmp, "arbiter.db")
    store = ResolutionStore(db_path)
    svc = get_service(store)
    actor = "operator:resolution-ops"

    # Authorities
    for aid, name, org in [("auth_polymarket_rules", "Polymarket market rules", "Polymarket"),
                           ("auth_kalshi_rules", "Kalshi contract terms", "Kalshi"),
                           ("auth_official_statements", "US/Iran official statements", "US State Dept / Iran MFA")]:
        store.save_authority(Authority(authority_id=aid, version=1, name=name, organization=org,
                                       source_type="rules" if "rules" in aid else "official_statement"), actor="system:intake")

    # Contracts (one per venue listing)
    contracts = {}
    for m, auth in [(PM, "auth_polymarket_rules"), (KS, "auth_kalshi_rules")]:
        cid = f"{m['venue']}:{m['market_id']}"
        store.save_contract(ResolutionSpecification(
            contract_id=cid, contract_version=1, title=m["question"],
            definition={"yes_if": m["criteria"]}, timing={"resolved_at": m["resolved_at"]},
            authority_ids=[auth, "auth_official_statements"],
            source_precedence=[auth, "auth_official_statements"],
            metadata={"venue": m["venue"], "cluster": "iran-nuclear-deal"}), actor="system:intake", status="active")
        contracts[m["venue"]] = cid

    # Evidence
    def ev(authority_id, contract_id, value, locator, observed):
        payload_hash = canonical_hash(value)
        rec = EvidenceRecord(evidence_id=gen_id("evid"), authority_id=authority_id, authority_version=1,
                             observed_at=observed, retrieved_at=utcnow(), normalized_value=value,
                             raw_payload_hash=payload_hash, parser_version="demo-0.1",
                             contract_id=contract_id, source_locator=locator)
        return store.append_evidence(rec, actor="system:evidence")

    e_mou = ev("auth_official_statements", contracts["kalshi"],
               {"event": "US-Iran Memorandum of Understanding", "date": "2026-06",
                "publicly_announced": True, "enrichment_limits": False, "centrifuge_caps": False,
                "sanctions_modification": False, "substance": "maintains status quo; defers commitments to future negotiations"},
               "public record, June 2026", "2026-06-30T00:00:00Z")
    e_pm = ev("auth_polymarket_rules", contracts["polymarket"],
              {"final_outcome": PM["outcome"], "resolved_at": PM["resolved_at"]},
              "gamma-api.polymarket.com/markets/521878", PM["resolved_at"])
    e_ks = ev("auth_kalshi_rules", contracts["kalshi"],
              {"final_outcome": KS["outcome"], "resolved_at": KS["resolved_at"],
               "venue_note": "June MOU ruled non-qualifying"},
              "api.elections.kalshi.com/trade-api/v2/markets/KXUSAIRANAGREEMENT-27-26SEP", KS["resolved_at"])

    before = store.summary()

    # Governed decision: the irreducible human judgment
    decision = svc.create(
        decision_type="policy_interpretation",
        question="Does the June 2026 US-Iran MOU constitute a qualifying nuclear agreement?",
        selection="non_qualifying",
        rationale=("The MOU maintained the status quo and deferred substantive commitments to future negotiations. "
                   "It contains no verifiable enrichment limits, centrifuge caps, or sanctions modification, so it does "
                   "not meet the formal-instrument threshold."),
        actor=actor,
        affected_case_ids=["KXUSAIRANAGREEMENT-27-26SEP", "KXUSAIRANAGREEMENT-27-26AUG", "521878"],
        cluster_id="iran-nuclear-deal",
        contract_id=contracts["kalshi"],
        governing_rule="YES requires a formal written instrument with verifiable nuclear restrictions AND sanctions relief.",
        controlling_authority_ids=["auth_kalshi_rules", "auth_official_statements"],
        controlling_evidence_ids=[e_mou["evidence_id"]],
        policy_basis={"class": "interpretive_criteria"},
    )

    # Propagation: queue as it stood when the MOU landed (June 2026).
    queue = {"items": [
        {"id": "KXUSAIRANAGREEMENT-27-26SEP", "status": "open"},
        {"id": "KXUSAIRANAGREEMENT-27-26AUG", "status": "open"},
        {"id": "521878", "status": "resolved"},      # Polymarket settled Jan 1 2026
        {"id": "527838", "status": "open"},          # unrelated: CPI March 2025
        {"id": "546814", "status": "open"},          # unrelated: Zelenskyy suit
    ]}
    applied = apply_decision_to_workflow(resolution_store=store, decision=decision,
                                         current_queue=queue, actor=actor)
    replay = apply_decision_to_workflow(resolution_store=store, decision=decision,
                                        current_queue=queue, actor=actor)
    after = store.summary()
    ws = store.list_work_states()

    chain = store.verify_audit_chain()
    audit = list(reversed(store.audit_log(limit=1000)))

    # Tamper test on a copy: rewrite the decision's audit details, re-verify.
    tdir = tempfile.mkdtemp(prefix="arbiter-tamper-")
    tpath = os.path.join(tdir, "arbiter.db")
    shutil.copy(db_path, tpath)
    con = sqlite3.connect(tpath)
    con.execute("UPDATE audit_events SET details_json=? WHERE action='decision.recorded'",
                (json.dumps({"selection": "qualifying"}),))
    con.commit(); con.close()
    tamper = ResolutionStore(tpath).verify_audit_chain()

    result = {
        "engine": "arbiter v0.34.0", "run_at": utcnow(),
        "markets": {"polymarket": PM, "kalshi": KS},
        "contracts": contracts,
        "evidence": [{"evidence_id": e["evidence_id"], "authority_id": e["authority_id"],
                      "source_locator": e["source_locator"], "record_hash": e["record_hash"],
                      "value": e["normalized_value"]} for e in (e_mou, e_pm, e_ks)],
        "decision": decision,
        "propagation": {"updated": applied["updated_case_ids"], "skipped": applied["skipped_case_ids"],
                        "untouched": ["527838", "546814"],
                        "replay_updated": replay["updated_case_ids"],
                        "work_states": ws, "boundary": applied.get("boundary")},
        "counts_before": before, "counts_after": after,
        "audit": audit, "chain": chain, "tamper_test": tamper,
    }
    with open(OUT, "w") as f:
        json.dump(result, f, indent=2, default=str)
    print(json.dumps({"decision_id": decision["decision_id"], "decision_hash": decision["decision_hash"],
                      "updated": applied["updated_case_ids"], "skipped": applied["skipped_case_ids"],
                      "replay_same": set(replay["updated_case_ids"]) == set(applied["updated_case_ids"]),
                      "chain": chain, "tamper": tamper, "audit_events": len(audit),
                      "semantic_counts_unchanged": all(before[k] == after[k] for k in
                          ("contracts", "authorities", "evidence_records", "resolution_runs"))}, indent=2))

if __name__ == "__main__":
    main()
