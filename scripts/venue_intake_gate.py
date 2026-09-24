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
  V15 fine print recurring across events (Kalshi pitcher props, rules quoted
      from the live API) is template; a clarification confined to one event
      (MOU-style) stays flagged however many of its markets repeat it
  V16 Kalshi discovery walks open events across pages and hosts, filters by
      event category (Sports excluded by default; allow-list honoured),
      skips parlays / rule-less / closed markets, and reports per-category counts
  V17 on the real Sep 24 2026 scan (600 markets, Kalshi via events by
      category), exactly the known 25 are flagged: long-dated economic markets
      whose rules pin the release, "next PM/chair" succession markets, "Zuppi"
      (not PPI) and venue death/role-definition fine print are not
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
    expected = ["3519811", "3539958", "3582091", "3697620", "4385336"] + [
        f"KXNCAAFTEAMRECTD-26SEP26UCLAMD-{t}" for t in ("MD2", "MD3", "MD4", "UCLA2", "UCLA3", "UCLA4")]
    check(flagged == sorted(expected),
          f"V13 exactly the 11 known markets are flagged on the real scan (got {len(flagged)})")

    # V15 standing fine print vs one-event clarification
    def pitcher(ticker, name, stat, n):
        return kalshi(ticker, f"{name}: {n}+ {stat}?",
                      f"If {name} records {n}+ {stat} in the Arizona vs Colorado professional baseball game "
                      "originally scheduled for Sep 23, 2026 at 8:40 PM EDT, then the market resolves to Yes.") | {
            "rules_secondary": (f"Player Participation & Settlement Criteria: If {name} is scratched or is not a starting "
                                f"pitcher, the market will resolve to the fair market price. If {name} is not a starting "
                                "pitcher but later enters the game, the market will resolve to the fair market price, "
                                "relief appearances will not count towards this market. If "
                                f"{name} is a starting pitcher and records at least one batter faced the market will "
                                f"settle based on {stat} recorded."),
            "event_ticker": ticker.rsplit("-", 1)[0]}
    mou = ("If the US and Iran sign a formal agreement with verifiable restrictions and sanctions relief, resolves Yes. "
           "The June 2026 memorandum of understanding does not count as an agreement for this market.")
    pool = [
        pitcher("KXMLBERA-26SEP232040AZCOL-AZMKELLY29-2", "Merrill Kelly", "earned runs", 2),
        pitcher("KXMLBERA-26SEP232040AZCOL-COLMADAMS38-2", "Mason Adams", "earned runs", 2),
        pitcher("KXMLBWA-26SEP232040AZCOL-AZMKELLY29-1", "Merrill Kelly", "walks allowed", 1),
        *[dict(kalshi(f"KXIRAN-27-26{mo}", "US-Iran deal?", mo and mou), event_ticker="KXIRAN-27")
          for mo in ("AUG", "SEP", "OCT", "NOV")],
        *[(kalshi(f"KXETH-{n}K", f"Ethereum above ${n},000?", f"Resolves Yes if Ethereum is above ${n},000 on Dec 31."))
          for n in range(3, 9)],
    ]
    ev15, _, st15 = venue_intake.discover(lambda venue, limit: [(m, "fixture") for m in pool] if venue == "kalshi" else [],
                                          limit=50)
    got15 = sorted(m for e in ev15 for _, m in e.markets)
    check(not any("KXMLB" in m for m in got15), "V15 pitcher props sharing fine print across two events are not flagged")
    check(got15 == ["KXIRAN-27-26AUG", "KXIRAN-27-26NOV", "KXIRAN-27-26OCT", "KXIRAN-27-26SEP"],
          "V15 an MOU-style clarification on 4 markets of ONE event stays flagged")

    # V17 real Sep 24 scan (Kalshi by category)
    with gzip.open(os.path.join(ROOT, "tests", "fixtures", "venue_scan_2026-09-24.json.gz"), "rt") as fh:
        scan24 = json.load(fh)["markets"]
    real24 = {"kalshi": [], "polymarket": []}
    for m in scan24:
        real24[m["venue"]].append((m["raw"], m["url"]))
    ev24, _, st24 = venue_intake.discover(lambda venue, limit: real24[venue], limit=5000)
    by_event = {e.event_id: sorted(m for _, m in e.markets) for e in ev24}
    check(st24["scanned"] == {"kalshi": 500, "polymarket": 100}, "V17 the Sep 24 scan has 600 open markets")
    check(sorted(by_event) == sorted(["kalshi-KXBRUVSEAT-35", "kalshi-KXG7LEADEROUT-26JUL20", "kalshi-KXXISUCCESSOR-45JAN01",
                                      "polymarket-848492", "polymarket-990651", "polymarket-1061890"]),
          f"V17 exactly the 6 known events are flagged (got {sorted(by_event)})")
    check(st24["flagged"] == {"kalshi": 22, "polymarket": 3}, f"V17 25 markets flagged (got {st24['flagged']})")
    flat24 = {m for ms in by_event.values() for m in ms}
    check(not any(t.startswith(("KXGDPYEAR", "KXUSCPIYEAR", "KXNOMGDPGROWTH", "KXU3EOY")) for t in flat24),
          "V17 economic markets whose rules pin the release are not flagged as revision-prone")
    check("KXNEWPOPE-70-MZUP" not in flat24, "V17 'Zuppi' is not the PPI series")
    check(not any(t.startswith(("KXNEXTDNCCHAIR", "KXNEXTNATOSECGEN", "KXNEXTROMANIAPM", "KXAFRICALEADEROUT")) for t in flat24),
          "V17 succession markets are not contested elections; shared role-definition fine print is template")

    # V16 Kalshi events by category
    def ev(ticker, title, category, markets):
        return {"event_ticker": ticker, "series_ticker": ticker.split("-")[0], "title": title,
                "category": category, "markets": markets}

    def nested(ticker, title, rules, status="active", **extra):
        m = {"ticker": ticker, "title": title, "rules_primary": rules, "rules_secondary": "", "status": status,
             "result": "", "close_time": "2026-12-31T00:00:00Z"}
        m.update(extra)
        return m

    clar = ("Resolves Yes if the NATO allies formally appoint a new Secretary General. "
            "An acting or interim appointment does not count as an appointment for this market.")
    page1 = {"cursor": "p2", "events": [
        ev("KXNBAGAME-26SEP23LALBOS", "Lakers at Celtics", "Sports",
           [nested("KXNBAGAME-26SEP23LALBOS-LAL", "Lakers win?", "If the Lakers win the game, resolves Yes.")]),
        ev("KXNEXTNATOSECGEN-99", "Who will be the next Secretary General of NATO?", "Elections",
           [nested(f"KXNEXTNATOSECGEN-99-{c}", f"{c} next NATO SG?", clar) for c in ("KIOH", "RUTT", "STOL")]),
    ]}
    page2 = {"cursor": "", "events": [
        ev("KXFEDDECISION-26OCT", "Fed decision in October", "Economics",
           [nested("KXFEDDECISION-26OCT-H0", "Fed holds?", "Resolves Yes if the target range is unchanged."),
            nested("KXFEDDECISION-26OCT-C25", "Fed cuts 25bp?", "Resolves Yes if the target range is cut by 25 bp.",
                   status="closed")]),
        ev("KXMVECROSS-1", "parlay", "Politics",
           [nested("KXMVECROSSCATEGORY-S1-A", "parlay leg", "", mve_collection_ticker="KXMVE")]),
    ]}
    pages = {"": page1, "p2": page2}
    calls = []

    def fake_json(url):
        calls.append(url)
        from urllib.parse import parse_qs, urlparse
        cursor = (parse_qs(urlparse(url).query).get("cursor") or [""])[0]
        return copy.deepcopy(pages[cursor])

    listed = venue_intake.list_kalshi_events(100, get_json=fake_json)
    tickers = sorted(m["ticker"] for m, _, _ in listed)
    check(len([c for c in calls if "cursor=p2" in c]) == 2, "V16 follows the cursor to page 2 on both hosts")
    check(tickers == ["KXFEDDECISION-26OCT-H0", "KXNEXTNATOSECGEN-99-KIOH", "KXNEXTNATOSECGEN-99-RUTT",
                      "KXNEXTNATOSECGEN-99-STOL"],
          "V16 sports excluded; parlay, rule-less and closed markets skipped; no duplicates across hosts")
    only = venue_intake.list_kalshi_events(100, categories=["economics"], exclude=[], get_json=fake_json)
    check([m["ticker"] for m, _, _ in only] == ["KXFEDDECISION-26OCT-H0"], "V16 category allow-list honoured (case-insensitive)")
    with_sports = venue_intake.list_kalshi_events(100, exclude=[], get_json=fake_json)
    check(any(m["ticker"].startswith("KXNBAGAME") for m, _, _ in with_sports), "V16 sports included when not excluded")
    kev, _, kst = venue_intake.discover(lambda venue, limit: listed if venue == "kalshi" else [], limit=100)
    nato = [e for e in kev if e.event_id == "kalshi-KXNEXTNATOSECGEN-99"]
    check(len(nato) == 1 and len(nato[0].markets) == 3 and nato[0].label.startswith("Who will be the next Secretary"),
          "V16 the NATO event's one-event clarification is flagged as ONE pattern, labelled with the event title")
    check(kst["by_category"]["kalshi"] == {"Elections": {"scanned": 3, "flagged": 3}, "Economics": {"scanned": 1, "flagged": 0}},
          "V16 per-category scanned/flagged counts reported")

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
    got_remaining = sorted(x["subject"].split("-", 1)[1] for x in remaining)
    held = {moved["subject"].split("-", 1)[1], decided_item["subject"].split("-", 1)[1]}
    check(got_remaining == sorted(set(flagged) - held),
          "V14 after re-triage the untouched queue holds exactly the real flags")
    # an item closed by re-triage comes back if the classifier flags it again;
    # one an operator resolved does not
    target = tri["closed"][0]["subject"]
    op_closed = tri["closed"][1]["subject"]
    op_id = venue_intake._exception_id(tri["closed"][1]["kind"], op_closed)
    tstore.set_work_state(evsvc.get_exception(op_id)["work_item_id"], "resolved", "Evan", "checked, fine", "operator:evan")
    same_class = next(k for k, v in venue_intake.ROUTING.items() if v[0] == tri["closed"][0]["kind"])
    pin_back = [venue_intake.WatchedEvent(
        event_id="again", label="again", review_class=same_class,
        markets=[(t.split("-", 1)[0].lower(), t.split("-", 1)[1]) for t in (target, op_closed)])]
    venue_intake.sync(tstore, pin_back, fetcher=noisy_fetch)
    reopened = evsvc.get_exception(venue_intake._exception_id(tri["closed"][0]["kind"], target))
    check(reopened["status"] == "open", "V14 an item closed by re-triage reopens when flagged again")
    check(evsvc.get_exception(op_id)["status"] == "resolved", "V14 an item an operator resolved stays resolved")

    closed_state = tstore.list_work_states()
    check(any("Closed by re-triage" in (v.get("note") or "") for v in closed_state.values()),
          "V14 each closure carries its reason")
    check(tstore.verify_audit_chain()["ok"] is True, "V14 audit chain intact after re-triage")

    check(store.verify_audit_chain()["ok"] is True, "audit chain intact after all syncs")
    print("VENUE INTAKE GATE: PASS")


if __name__ == "__main__":
    main()
