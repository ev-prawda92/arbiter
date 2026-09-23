#!/usr/bin/env python3
"""Release gate for Arbiter v0.36 live venue intake (offline).

Runs the real intake pipeline against canned venue API responses (synthetic,
shaped like Kalshi trade-api v2 and Polymarket gamma-api), so CI never needs
the network. Properties asserted (fail-closed):

  V1 markets that need a human judgment become work items; a dual-listed
     event's markets form ONE work pattern
  V2 a clean price-threshold market is tracked (contract + evidence) with no work item
  V3 evidence is hashed from the full raw venue response
  V4 re-sync with unchanged data writes nothing (no evidence, no audit events)
  V5 a governed decision clears the event's pattern, and re-sync keeps it cleared
  V6 a market that settles gets new evidence (superseding the old) and its
     intake work item closes with the venue's outcome
  V7 a change to the venue's rules text creates a new contract version
  V8 one failing market is reported and never blocks the others
  V9 venues that settle differently open a critical cross-venue work item
  V10 --dry-run writes nothing at all
  V11 discovery scans open markets, skips parlays / settled / clean ones, and
      groups a venue event's flagged markets into one work pattern
  V12 no false alarms from venue templates or sports "win the" wording
  V13 on the real Sep 23 2026 scan (300 open markets captured from the live
      APIs), exactly the known 5 markets are flagged - a precision regression
  V14 re-triage closes untouched intake work the classifier no longer flags,
      and never touches operator-moved, decision-covered or watchlist-pinned work
"""
from __future__ import annotations

import copy
import gzip
import json
import os
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "backend"))

from app import operations_intelligence, venue_intake, workflow  # noqa: E402
from app.active_evidence import get_service as get_evidence_service  # noqa: E402
from app.decision_operations import apply_authoritative_decisions  # noqa: E402
from app.decision_records import DecisionRecordService  # noqa: E402
from app.resolution_infra import ResolutionStore, canonical_hash  # noqa: E402

IRAN_RULES = ("If, before the close date, the United States and Iran sign a formal written agreement that "
              "places verifiable restrictions on Iran's enrichment or centrifuge program and provides for the "
              "lifting or modification of sanctions, the market resolves to Yes.")


def kalshi(ticker, title, rules, status="active", result=""):
    return {"ticker": ticker, "event_ticker": ticker.rsplit("-", 1)[0], "title": title,
            "rules_primary": rules, "rules_secondary": "", "status": status, "result": result,
            "close_time": "2026-09-01T14:00:00Z", "settlement_ts": "2026-09-01T15:00:00Z" if result else None,
            "yes_bid": 7, "volume": 120345}


def poly(mid, question, description, closed=False, prices=("0.42", "0.58"), uma="", disputes=0):
    return {"id": mid, "question": question, "description": description, "resolutionSource": "",
            "closed": closed, "outcomes": json.dumps(["Yes", "No"]), "outcomePrices": json.dumps(list(prices)),
            "umaResolutionStatus": uma, "umaResolutionStatuses": json.dumps(["proposed"] + ["disputed"] * disputes),
            "closedTime": "2026-01-01T08:00:00Z" if closed else None, "umaEndDate": None, "volume": "88123.4"}


FIXTURES = {
    ("kalshi", "KXIRANDEAL-26SEP"): kalshi("KXIRANDEAL-26SEP", "Will the US agree to a new Iranian nuclear deal?", IRAN_RULES),
    ("kalshi", "KXIRANDEAL-26AUG"): kalshi("KXIRANDEAL-26AUG", "Will the US agree to a new Iranian nuclear deal?", IRAN_RULES),
    ("polymarket", "900001"): poly("900001", "US-Iran nuclear deal in 2025?",
                                   "Resolves Yes if an official agreement is announced, per a consensus of credible reporting.",
                                   closed=True, prices=("0", "1"), uma="resolved"),
    ("kalshi", "KXBTC-100K"): kalshi("KXBTC-100K", "Bitcoin above $100,000 on Dec 31?",
                                     "Resolves Yes if the Bitcoin price is above $100,000 at 23:59 ET on Dec 31."),
    ("polymarket", "900002"): poly("900002", "US CPI above 3.0% in August?",
                                   "Resolves per the BLS CPI release for August."),
    ("kalshi", "KXSHUTDOWN-Q4"): kalshi("KXSHUTDOWN-Q4", "Government shutdown in Q4?", "Resolves Yes if a lapse in appropriations begins.",
                                        status="settled", result="yes"),
    ("polymarket", "900003"): poly("900003", "Government shutdown in Q4?", "Resolves Yes if a lapse in appropriations begins.",
                                   closed=True, prices=("0", "1"), uma="resolved"),
}

WATCHLIST = [
    {"seed_event_id": "iran-deal", "label": "US-Iran nuclear deal", "review_class": "interpretive_criteria",
     "kalshi": ["KXIRANDEAL-26SEP", "KXIRANDEAL-26AUG"], "polymarket": ["900001"]},
    {"seed_event_id": "btc-100k", "label": "BTC above 100k", "kalshi": ["KXBTC-100K"]},
    {"seed_event_id": "cpi-aug", "label": "US CPI August", "polymarket": ["900002"]},
    {"seed_event_id": "shutdown-q4", "label": "Q4 shutdown", "kalshi": ["KXSHUTDOWN-Q4"], "polymarket": ["900003"]},
    {"seed_event_id": "broken", "label": "Missing market", "polymarket": ["999999"]},
]


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)
    print(f"[PASS] {message}")


def make_fetcher(fixtures):
    def fetch(venue, market_id):
        raw = fixtures.get((venue, market_id))
        if raw is None:
            raise LookupError(f"{venue} market {market_id} not found")
        return copy.deepcopy(raw), f"fixture://{venue}/{market_id}"
    return fetch


def queue_for(store: ResolutionStore) -> dict:
    infra = {"authorities": [], "audit_chain": {"ok": True},
             "evidence_exceptions": get_evidence_service(store).list_exceptions(active_only=True)}
    queue = workflow.build_work_queue([], {}, infra, store.list_work_states())
    return apply_authoritative_decisions(queue, DecisionRecordService(store).authoritative(limit=500))


def audit_count(store: ResolutionStore) -> int:
    return store.verify_audit_chain()["events"]


def main() -> None:
    tmp = tempfile.mkdtemp(prefix="arbiter-v036-intake-")
    watch_path = os.path.join(tmp, "watch.jsonl")
    with open(watch_path, "w") as fh:
        fh.write("\n".join(json.dumps(r) for r in WATCHLIST) + "\n")
    events = venue_intake.load_watchlist(watch_path)

    # V10 dry run first, on its own store
    dry_store = ResolutionStore(os.path.join(tmp, "dry.db"))
    dry = venue_intake.sync(dry_store, events, fetcher=make_fetcher(FIXTURES), dry_run=True)
    check(audit_count(dry_store) == 0 and dry_store.summary()["contracts"] == 0,
          "V10 dry run writes nothing (0 audit events, 0 contracts)")
    check(len(dry["markets"]) == 7, "V10 dry run still fetches and classifies every reachable market")

    store = ResolutionStore(os.path.join(tmp, "arbiter.db"))
    fixtures = copy.deepcopy(FIXTURES)
    report = venue_intake.sync(store, events, fetcher=make_fetcher(fixtures))
    by = {(m["venue"], m["market_id"]): m for m in report["markets"]}

    # V8
    check(len(report["errors"]) == 1 and report["errors"][0]["market_id"] == "999999",
          "V8 the missing market is reported as an error")
    check(len(report["markets"]) == 7, "V8 every other market still synced (7)")

    # V1
    check(by[("kalshi", "KXIRANDEAL-26SEP")]["work_item"] == "opened"
          and by[("kalshi", "KXIRANDEAL-26AUG")]["work_item"] == "opened",
          "V1 both open Iran markets opened work items")
    check(by[("polymarket", "900002")]["review_class"] == "revised_source"
          and by[("polymarket", "900002")]["work_item"] == "opened",
          "V1 CPI market routed as revision-prone and opened a work item")
    queue = queue_for(store)
    ops = operations_intelligence.analyze_queue(queue)
    iran_ids = {by[("kalshi", t)]["work_item_id"] for t in ("KXIRANDEAL-26SEP", "KXIRANDEAL-26AUG")}
    iran_cluster = next(c for c in ops["clusters"] if iran_ids <= set(c["case_ids"]))
    check(iran_cluster["count"] == 2 and iran_cluster["blocker_type"] == "policy_interpretation",
          "V1 the two Iran markets form ONE policy-interpretation work pattern")

    # V2
    btc = by[("kalshi", "KXBTC-100K")]
    check(btc["work_item"] == "none" and btc["contract_id"] and btc["evidence_id"],
          "V2 clean threshold market tracked with contract + evidence, no work item")

    # V3
    ev = next(e for e in store.list_evidence("kalshi:KXIRANDEAL-26SEP") if e["evidence_id"] == by[("kalshi", "KXIRANDEAL-26SEP")]["evidence_id"])
    check(ev["raw_payload_hash"] == canonical_hash(FIXTURES[("kalshi", "KXIRANDEAL-26SEP")]),
          "V3 evidence raw_payload_hash is the hash of the full raw venue response")

    # V9
    check(report["totals"]["cross_venue_disagreements"] == 1, "V9 shutdown event detected as a cross-venue disagreement")
    xv = get_evidence_service(store).get_exception(venue_intake._exception_id("evidence_conflict", "EVENT-shutdown-q4"))
    check(xv and xv["severity"] == "critical" and xv["status"] == "open", "V9 a critical cross-venue work item is open")

    # V4
    before_audit, before_counts = audit_count(store), store.summary()
    fixtures[("kalshi", "KXIRANDEAL-26SEP")]["yes_bid"] = 9  # price tick only
    again = venue_intake.sync(store, events, fetcher=make_fetcher(fixtures))
    check(again["totals"]["evidence_appended"] == 0 and again["totals"]["work_items_opened"] == 0,
          "V4 re-sync with only price changes appends no evidence and opens nothing")
    check(audit_count(store) == before_audit and store.summary()["evidence_records"] == before_counts["evidence_records"],
          "V4 re-sync writes no audit events")

    # V5
    svc = DecisionRecordService(store)
    svc.create(decision_type="policy_interpretation", question="Does the MOU count as a deal?",
               selection="MOU is non-qualifying", rationale="No verifiable restrictions or sanctions relief.",
               actor="operator:gate", affected_case_ids=list(iran_cluster["case_ids"]),
               cluster_id=iran_cluster["cluster_id"])
    cleared = {i["id"] for i in queue_for(store)["items"] if i.get("governed_by")}
    check(iran_ids <= cleared, "V5 the governed decision clears both Iran work items")
    venue_intake.sync(store, events, fetcher=make_fetcher(fixtures))
    cleared_after = {i["id"] for i in queue_for(store)["items"] if i.get("governed_by")}
    check(iran_ids <= cleared_after, "V5 re-sync leaves the decision-cleared items cleared")

    # V6
    fixtures[("polymarket", "900002")].update(closed=True, outcomePrices=json.dumps(["1", "0"]), umaResolutionStatus="resolved")
    settled = venue_intake.sync(store, events, fetcher=make_fetcher(fixtures))
    cpi = next(m for m in settled["markets"] if m["market_id"] == "900002")
    check(cpi["status"] == "settled" and cpi["outcome"] == "YES" and cpi["evidence_id"], "V6 settlement appends new evidence")
    cpi_ev = [e for e in store.list_evidence("polymarket:900002") if e["authority_id"] == "auth_polymarket_rules"]
    newest = max(cpi_ev, key=lambda e: e["revision_number"])
    check(newest["revision_number"] == 2 and newest["supersedes"], "V6 the new evidence supersedes the open-market evidence")
    check(cpi["work_item"] == "closed", "V6 the intake work item closed on settlement")
    wid = by[("polymarket", "900002")]["work_item_id"]
    state = store.list_work_states()[wid]
    check(state["status"] == "resolved" and "settled YES" in state["note"], "V6 the closed item carries the venue outcome")

    # V7
    fixtures[("kalshi", "KXBTC-100K")]["rules_primary"] += " Price per the CF Benchmarks index."
    changed = venue_intake.sync(store, events, fetcher=make_fetcher(fixtures))
    btc2 = next(m for m in changed["markets"] if m["market_id"] == "KXBTC-100K")
    check(btc2["contract_version"] == 2 and btc2["contract_version_created"], "V7 rules change creates contract version 2")

    # V11 discovery
    vague = "Resolves Yes per a consensus of credible reporting that a ceasefire is in effect."
    listings = {
        "kalshi": [
            (kalshi("KXCEASE-26-OCT", "Ceasefire by October?", vague), "fixture://k/1"),
            (kalshi("KXCEASE-26-NOV", "Ceasefire by November?", vague), "fixture://k/2"),
            (kalshi("KXBTC-120K", "Bitcoin above $120,000?", "Resolves Yes if Bitcoin is above $120,000 on Dec 31."), "fixture://k/3"),
            # a realistic pool: sports markets that say "win the", and clean thresholds
            *[(kalshi(f"KXWNBA{q}QWINNER-26SEP23DALSEA-SEA", f"Will Seattle win the {q}th quarter?",
                      f"If Seattle wins the {q}th quarter of the game, the market resolves to Yes. Winner of the quarter per the official box score."),
               f"fixture://k/q{q}") for q in range(1, 5)],
            *[(kalshi(f"KXETH-{n}K", f"Ethereum above ${n},000?", f"Resolves Yes if Ethereum is above ${n},000 on Dec 31."),
               f"fixture://k/e{n}") for n in range(3, 9)],
            (dict(kalshi("KXMVECROSS-1", "parlay", vague), mve_collection_ticker="KXMVE"), "fixture://k/4"),
            (kalshi("KXDONE-1", "Already settled", vague, status="settled", result="no"), "fixture://k/5"),
        ],
        "polymarket": [
            (dict(poly("910001", "CPI above 3% in October?", "Resolves per the BLS CPI release for October."),
                  events=[{"id": "e77", "title": "US CPI October"}]), "fixture://p/1"),
            # Polymarket's standard template wording on ordinary markets
            *[(dict(poly(f"92000{n}", f"Will team {n} make the playoffs?",
                         "This market will resolve to Yes if the team qualifies. The primary resolution source will be "
                         "official league information, however a consensus of credible reporting may also be used."),
                    events=[{"id": f"s{n}", "title": f"Team {n} playoffs"}]), f"fixture://p/s{n}") for n in range(1, 10)],
        ],
    }
    found, cached_fetch, stats = venue_intake.discover(lambda venue, limit: listings[venue], limit=50)
    keys = {e.event_id: sorted(m for _, m in e.markets) for e in found}
    check(stats["scanned"] == {"kalshi": 15, "polymarket": 10}, "V11 discovery scanned every listed open market")
    check(keys.get("kalshi-KXCEASE-26") == ["KXCEASE-26-NOV", "KXCEASE-26-OCT"],
          "V11 the two ceasefire markets are grouped under one Kalshi event")
    check("polymarket-e77" in keys and not any("BTC" in k or "ETH" in k or "MVE" in k or "DONE" in k for ks in keys.values() for k in ks),
          "V11 CPI kept; clean threshold, parlay and settled markets skipped")
    check(not any("WNBA" in k for ks in keys.values() for k in ks),
          "V12 sports 'win the quarter' markets are not flagged as contested official sources")
    check(not any(k.startswith("polymarket-s") for k in keys),
          "V12 Polymarket's template 'consensus of credible reporting' alone does not flag a market")
    check("consensus of credible reporting" in stats["boilerplate"]["polymarket"],
          "V12 discovery learned the Polymarket template wording from the scan")
    dstore = ResolutionStore(os.path.join(tmp, "discover.db"))
    drep = venue_intake.sync(dstore, found, fetcher=cached_fetch)
    dops = operations_intelligence.analyze_queue(queue_for(dstore))
    cease = [c for c in dops["clusters"] if c["count"] == 2]
    check(drep["totals"]["work_items_opened"] == 3 and len(cease) == 1,
          "V11 discovered markets land in the queue; the ceasefire pair is one work pattern")

    # V13 real-scan precision
    scan_path = os.path.join(ROOT, "tests", "fixtures", "venue_scan_2026-09-23.json.gz")
    with gzip.open(scan_path, "rt") as fh:
        scan = json.load(fh)["markets"]
    real = {"kalshi": [], "polymarket": []}
    for m in scan:
        real[m["venue"]].append((m["raw"], m["url"]))
    real_events, real_fetch, real_stats = venue_intake.discover(lambda venue, limit: real[venue], limit=1000)
    flagged = sorted(m for e in real_events for _, m in e.markets)
    check(real_stats["scanned"] == {"kalshi": 200, "polymarket": 100}, "V13 the real scan has 300 open markets")
    check(flagged == ["3519811", "3539958", "3582091", "3697620", "4385336"],
          f"V13 exactly the 5 known markets are flagged on the real scan (got {len(flagged)})")

    # V14 re-triage
    tstore = ResolutionStore(os.path.join(tmp, "retriage.db"))
    noisy_events, noisy_fetch, _ = venue_intake.discover(lambda venue, limit: real[venue], limit=1000, include_all=True)
    venue_intake.sync(tstore, noisy_events, fetcher=noisy_fetch, boilerplate={})  # pre-fix behaviour: no template learning
    evsvc = get_evidence_service(tstore)
    opened = [x for x in evsvc.list_exceptions() if (x.get("metadata") or {}).get("source") == "venue_intake"]
    check(len(opened) > 50, f"V14 setup: the pre-fix sync opened a noisy queue ({len(opened)} items)")
    moved, decided_item = opened[0], opened[1]
    tstore.set_work_state(moved["work_item_id"], "in_progress", "Evan", "looking at it", "operator:evan")
    DecisionRecordService(tstore).create(decision_type="policy_interpretation", question="q", selection="s",
                                         rationale="r", actor="operator:gate",
                                         affected_case_ids=[decided_item["work_item_id"]], cluster_id="c")
    pinned_events = [venue_intake.WatchedEvent(event_id="pinned", label="pinned", review_class="interpretive_criteria",
                                               markets=[("kalshi", real["kalshi"][0][0]["ticker"])])]
    venue_intake.sync(tstore, pinned_events, fetcher=noisy_fetch, boilerplate={})
    open_before, audit_before = len(evsvc.list_exceptions()), audit_count(tstore)
    preview = venue_intake.retriage(tstore, dry_run=True)
    check(len(evsvc.list_exceptions()) == open_before and audit_count(tstore) == audit_before,
          "V14 dry-run re-triage writes nothing")
    tri = venue_intake.retriage(tstore)
    check(tri["totals"]["closed"] == preview["totals"]["closed"] > 0, f"V14 re-triage closed {tri['totals']['closed']} stale items")
    still_open = {x["work_item_id"] for x in evsvc.list_exceptions() if x["status"] != "resolved"}
    check(moved["work_item_id"] in still_open, "V14 an item an operator moved is left alone")
    check(decided_item["work_item_id"] in still_open, "V14 an item a decision covers is left alone")
    pinned_id = venue_intake._exception_id("policy_review", "KALSHI-" + real["kalshi"][0][0]["ticker"])
    check(evsvc.get_exception(pinned_id)["status"] == "open", "V14 a watchlist-pinned item is left alone")
    remaining = [x for x in evsvc.list_exceptions() if x["status"] != "resolved"
                 and x["work_item_id"] not in {moved["work_item_id"], decided_item["work_item_id"]}
                 and x["exception_id"] != pinned_id]
    check(sorted(x["subject"].split("-", 1)[1] for x in remaining) == flagged,
          "V14 after re-triage the untouched queue holds exactly the 5 real flags")
    closed_state = tstore.list_work_states()
    check(any("Closed by re-triage" in (v.get("note") or "") for v in closed_state.values()),
          "V14 each closure carries its reason")
    check(tstore.verify_audit_chain()["ok"] is True, "V14 audit chain intact after re-triage")

    check(store.verify_audit_chain()["ok"] is True, "audit chain intact after all syncs")
    print("VENUE INTAKE GATE: PASS")


if __name__ == "__main__":
    main()
