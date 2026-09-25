#!/usr/bin/env python3
"""Release gate for Arbiter v0.39: the precedent engine.

Every governed decision becomes precedent; new contracts are checked against
it on arrival; departing from an applicable precedent must be distinguished or
overruled; appeals and questions are answered from the record, with citations.

Properties asserted (fail-closed), all on real Kalshi/Polymarket markets from
the recorded Sep 23-24 2026 scans:

  P1  matching accuracy: at the same-template threshold, cross-event recall
      >= 0.75 with precision 1.0 against template families, no wrong top-1 at
      any score, and exactly the 5 reviewed no-family pairs above threshold
  P2  clause reach: exactly the 2 reviewed cross-event clause links
  P3  a decision becomes a precedent with its contracts and ruled clauses (audited)
  P4  the next event of a decided series matches on arrival: same clause,
      same series, routed to work with the ruling in the detail, recorded + audited
  P5  no unrelated market in the scan matches a precedent at an applicable tier
  P6  the decision workbench is shown the applicable precedent and the clause
  P7  departing without a distinction is refused (409); with one it is recorded,
      audited, and the precedent stays live
  P8  following a precedent is recognized and cited on the new decision
  P9  overruling is prospective: the precedent retires, the old decision stays
      authoritative for its own cases, and new contracts no longer match it
  P10 appeal checks name the governing ruling and verdict, audited
  P11 Ask Arbiter answers from the record with citations, and says so when
      nothing covers the question
  P12 superseding a decision retires its precedent
  P13 standing fine print never carries a ruling
  P14 re-triage leaves precedent-routed work alone
  P15 precedent operations never touch contracts, evidence, resolutions or
      settlement; the audit chain verifies end to end
  P16 read endpoints (list, match, ask, context, consistency preview) write nothing
  P17 an overrule retires the whole line of precedent however long it is, and a
      repeated or concurrent overrule is a no-op
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
sys.path.insert(0, os.path.join(ROOT, "scripts"))

_tmp = tempfile.mkdtemp(prefix="arbiter-v039-precedent-")
os.environ["ARBITER_DATABASE_PATH"] = os.path.join(_tmp, "arbiter.db")
os.environ.setdefault("ARBITER_POLICY_PATH", os.path.join(_tmp, "policy.json"))

import precedent_eval  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import precedents as P  # noqa: E402
from app import venue_intake as vi  # noqa: E402
from app.decision_records import get_service as get_decisions  # noqa: E402
from app.server import app, resolution_store as store  # noqa: E402

REVIEWED_NO_FAMILY = {  # same template under another ticker; reviewed by hand
    ("kalshi:KXPERSONPRESFUENTES-45", "kalshi:KXPERSONPRESMAM-45"),
    ("kalshi:KXPERSONPRESMAM-45", "kalshi:KXPERSONPRESFUENTES-45"),
    ("polymarket:4873310", "polymarket:4782237"),
    ("polymarket:3866284", "polymarket:4844895"),
    ("polymarket:4844895", "polymarket:3866284"),
}
REVIEWED_CLAUSE_LINKS = {  # "official results ... as published by the state electoral authority"
    ("834406", "polymarket:3697620"),
    ("870884", "polymarket:3519811"),
}
G7_RULING = "Death in office counts as leaving office; resolve on the date the office is vacated"
CCP_RULING = (
    "Only a permanent General Secretary named by the Central Committee counts; interim or acting leaders do not"
)
DEPART = "Only resignation or removal counts; death does not count as leaving office"


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)
    print(f"[PASS] {message}")


def audit_actions(object_id: str | None = None) -> list[str]:
    return [e["action"] for e in store.audit_log(limit=5000, object_id=object_id)]


def scan(name: str) -> dict[str, list]:
    with gzip.open(os.path.join(ROOT, "tests", "fixtures", name), "rt") as fh:
        markets = json.load(fh)["markets"]
    out: dict[str, list] = {"kalshi": [], "polymarket": []}
    for m in markets:
        out[m["venue"]].append((m["raw"], m["url"]))
    return out


def next_event(pool: dict[str, list], series: str, old: str, new: str, old_date: str, new_date: str) -> list:
    out = []
    for raw, url in pool["kalshi"]:
        if str(raw.get("event_ticker", "")).startswith(series):
            r = copy.deepcopy(raw)
            r["event_ticker"] = r["event_ticker"].replace(old, new)
            r["ticker"] = r["ticker"].replace(old, new)
            r["rules_primary"] = str(r.get("rules_primary") or "").replace(old_date, new_date)
            out.append((r, f"{url}#{new}"))
    return out


def ingest(lister_pool: dict[str, list]) -> dict:
    events, fetcher, stats = vi.discover(lambda v, limit: lister_pool.get(v, []), limit=5000, store=store)
    return vi.sync(store, events, fetcher=fetcher, boilerplate=stats["boilerplate"])


def clusters(client) -> list[dict]:
    return client.get("/api/overview").json()["agent_brief"]["operations_intelligence"]["clusters"]


def main() -> int:
    # P1-P2: measured on real markets
    res = precedent_eval.evaluate()
    at = res["thresholds"][f"{P.SAME_TEMPLATE:.2f}"]
    check(res["markets"] == 838, f"P1 evaluation covers the 838 distinct real markets (got {res['markets']})")
    check(
        at["recall"] >= 0.75 and at["precision"] == 1.0,
        f"P1 same-template: cross-event recall {at['recall']} >= 0.75 at precision {at['precision']}",
    )
    check(not res["top1_wrong_family"], "P1 no wrong-family top match at any score")
    pairs = {
        (
            f["market"].split(":")[0] + ":" + f["market"].split(":")[1],
            f["matched"].split(":")[0] + ":" + f["matched"].split(":")[1],
        )
        for f in res["no_family_matches_at_threshold"]
    }
    check(
        pairs == REVIEWED_NO_FAMILY,
        f"P1 exactly the 5 reviewed same-template pairs clear the threshold (got {len(pairs)})",
    )
    links = {(r["event"], h["contract"]) for r in res["clause_reach"] for h in r["applies_elsewhere"]}
    check(links == REVIEWED_CLAUSE_LINKS, f"P2 exactly the 2 reviewed cross-event clause links (got {sorted(links)})")

    client = TestClient(app)
    pool24 = scan("venue_scan_2026-09-24.json.gz")
    rep = ingest(pool24)
    check(
        rep["totals"]["work_items_opened"] == 22,
        "P3 setup: the Sep 24 scan opens its 22 known work items (v0.43 triage)",
    )
    by_count = {c["count"]: c for c in clusters(client)}
    ccp, g7 = by_count[14], by_count[7]

    # P3
    r = client.post(
        "/api/decisions",
        json={
            "cluster_id": g7["cluster_id"],
            "selection": G7_RULING,
            "rationale": "For 'first to leave office' the vacancy date controls for every market in the event.",
            "governing_rule": "First departure is the earliest date an office is vacated for any reason",
        },
    )
    check(r.status_code == 200 and r.json()["consistency"]["status"] == "novel", "P3 first G7 ruling records as novel")
    g7_id = r.json()["decision"]["decision_id"]
    g7_prec = P.get_engine(store).get(g7_id)
    check(
        len(g7_prec["contracts"]) == 7 and any("death" in c["text"].lower() for c in g7_prec["clauses"]),
        "P3 the precedent holds all 7 decided contracts and the death clause that was ruled on",
    )
    check("precedent.created" in audit_actions(g7_id), "P3 precedent creation is in the audit chain")
    r = client.post(
        "/api/decisions",
        json={
            "cluster_id": ccp["cluster_id"],
            "selection": CCP_RULING,
            "rationale": "Interim and acting leaders are excluded unless later announced as permanent.",
            "governing_rule": "Official party announcement of a permanent leader controls",
        },
    )
    check(r.status_code == 200 and r.json()["precedent"]["clauses"] == 3, "P3 CCP ruling becomes a 3-clause precedent")
    ccp_id = r.json()["decision"]["decision_id"]

    # P4 next G7 event arrives
    counts_before = store.summary()
    nxt = next_event(pool24, "KXG7LEADEROUT", "26JUL20", "27JAN20", "Jul 20, 2026", "Jan 20, 2027")
    rep = ingest({"kalshi": nxt})
    ms = rep["markets"]
    check(len(ms) == 7, "P4 all 7 markets of the next G7 event come in")
    check(
        all(
            m.get("precedent", {}).get("precedent_id") == g7_id and m["precedent"]["tier"] == "same_clause" for m in ms
        ),
        "P4 every one matches the G7 ruling on the same clause",
    )
    check(all(m["precedent"]["relation"] == "same_series" for m in ms), "P4 the match is labelled same series")
    check(rep["totals"]["work_items_opened"] == 7, "P4 each opens a work item")
    exc = next(e for e in vi.get_evidence_service(store).list_exceptions() if "27JAN20" in e["subject"])
    check(g7_id in exc["detail"] and "applies" in exc["detail"], "P4 the work item says which ruling applies")
    check(
        len(P.get_engine(store).matches_for(g7_id)) == 7 and "precedent.matched" in audit_actions(exc["contract_id"]),
        "P4 matches are recorded and audited",
    )
    check(store.summary()["resolution_runs"] == counts_before["resolution_runs"], "P4 matching resolves nothing")

    # P5 unrelated markets
    engine = P.get_engine(store)
    live = engine.list()
    corpus = engine.corpus()
    stray = []
    for venue, items in pool24.items():
        for raw, url in items:
            row = vi.normalize(venue, raw, url)
            if not row["rules"] or "KXG7LEADEROUT" in str(row["event_id"]) or "KXXISUCCESSOR" in str(row["event_id"]):
                continue
            row["contract_id"] = f"{venue}:{row['market_id']}"
            if engine.match(row, precedents=live, corpus=corpus, min_tier="same_template"):
                stray.append(row["contract_id"])
    check(not stray, f"P5 none of the other scanned markets matches at an applicable tier (got {stray[:5]})")

    # P6 workbench context for the pattern the new event landed in
    pattern = next(c for c in clusters(client) if c["count"] == 7)
    ctx = client.get(f"/api/decision-context/{pattern['cluster_id']}").json()
    top = (ctx.get("precedent_matches") or [{}])[0]
    check(
        top.get("precedent_id") == g7_id and top.get("tier") == "same_clause" and top.get("matched_clause"),
        "P6 the workbench shows the applicable G7 precedent with the matched clause",
    )

    # P7 departing
    r = client.post(
        "/api/decisions", json={"cluster_id": pattern["cluster_id"], "selection": DEPART, "rationale": "new view"}
    )
    check(
        r.status_code == 409 and r.json()["detail"]["code"] == "precedent_conflict",
        "P7 departing from precedent without a distinction is refused",
    )
    prev = client.post(
        "/api/decisions/consistency", json={"cluster_id": pattern["cluster_id"], "selection": G7_RULING}
    ).json()
    check(prev["status"] == "consistent", "P8 preview: the same ruling reads as consistent")
    prev = client.post(
        "/api/decisions/consistency",
        json={"cluster_id": pattern["cluster_id"], "selection": G7_RULING, "precedent_ids": [g7_id]},
    ).json()
    check(prev["status"] == "follows", "P8 preview: citing it reads as follows")
    r = client.post(
        "/api/decisions",
        json={
            "cluster_id": pattern["cluster_id"],
            "selection": DEPART,
            "rationale": "The Jan 2027 series terms exclude death.",
            "distinguish": "The Jan 2027 terms exclude death explicitly; the Jul 2026 terms did not.",
        },
    )
    check(r.status_code == 200 and r.json()["consistency"]["status"] == "divergent", "P7 a stated distinction records")
    check("precedent.distinguished" in audit_actions(g7_id), "P7 the distinction is audited against the precedent")
    check(engine.get(g7_id)["state"] == "active", "P7 distinguishing leaves the precedent live")

    # P8 follow on a third event
    third = next_event(pool24, "KXG7LEADEROUT", "26JUL20", "27JUL20", "Jul 20, 2026", "Jul 20, 2027")
    ingest({"kalshi": third})
    pattern = next(c for c in clusters(client) if c["count"] == 7)
    r = client.post(
        "/api/decisions",
        json={
            "cluster_id": pattern["cluster_id"],
            "selection": G7_RULING,
            "rationale": "Same terms as the Jul 2026 event.",
            "precedent_ids": [g7_id],
        },
    )
    body = r.json()
    check(
        r.status_code == 200
        and body["consistency"]["status"] == "follows"
        and g7_id in body["decision"]["precedent_ids"],
        "P8 following the precedent is recognized and cited on the record",
    )
    check(
        len(body["consistency"].get("conflicting") or []) == 2,
        "P8 the split between the original and the distinguished ruling is surfaced",
    )

    # P9 overrule on a fourth event
    fourth = next_event(pool24, "KXG7LEADEROUT", "26JUL20", "28JAN20", "Jul 20, 2026", "Jan 20, 2028")
    ingest({"kalshi": fourth})
    pattern = next(c for c in clusters(client) if c["count"] == 7)
    ctx = client.get(f"/api/decision-context/{pattern['cluster_id']}").json()
    governing = next(
        m["precedent_id"] for m in ctx["precedent_matches"] if P.agrees(m["ruling"]["selection"], G7_RULING)
    )
    r = client.post(
        "/api/decisions",
        json={
            "cluster_id": pattern["cluster_id"],
            "selection": DEPART,
            "rationale": "The venue has clarified that 'leave office' means resignation or removal.",
            "overrules": governing,
        },
    )
    check(r.status_code == 200, f"P9 an explicit overrule records (got {r.status_code})")
    new_id = r.json()["decision"]["decision_id"]
    check(engine.get(governing)["state"] == "overruled", "P9 the overruled precedent retires")
    check(
        engine.get(g7_id)["state"] == "overruled" and set(r.json()["consistency"]["overruled"]) >= {g7_id, governing},
        "P9 the whole line holding that ruling retires with it",
    )
    check(not get_decisions(store).is_superseded(governing), "P9 the overruled decision still governs its own cases")
    probe = vi.normalize("kalshi", fourth[0][0], fourth[0][1]) | {"contract_id": "kalshi:PROBE"}
    ids = [m["precedent_id"] for m in engine.match(probe, min_tier="same_template")]
    check(governing not in ids and new_id in ids, "P9 new contracts now match the overruling decision instead")

    # P10 appeals
    ap = client.post(
        "/api/appeals/check",
        json={
            "contract_id": "kalshi:KXG7LEADEROUT-26JUL20-DJT",
            "requested_selection": DEPART,
            "grounds": "A trader argues death is not departure.",
        },
    ).json()
    check(
        ap["verdict"] == "contradicts_ruling" and ap["governing_decision"]["precedent_id"] == g7_id,
        "P10 an appeal against the governing ruling is identified, with the ruling it contradicts",
    )
    check("appeal.checked" in audit_actions("kalshi:KXG7LEADEROUT-26JUL20-DJT"), "P10 the appeal check is audited")
    ap = client.post(
        "/api/appeals/check",
        json={"contract_id": "kalshi:KXXISUCCESSOR-45JAN01-LQIA", "requested_selection": CCP_RULING},
    ).json()
    check(ap["verdict"] == "matches_ruling", "P10 an appeal asking for the existing ruling is recognized as moot")

    # P11 Ask Arbiter
    a = client.post("/api/ask", json={"question": "Do acting or interim party leaders count?"}).json()
    check(
        a["grounded"] and a["citations"][0]["precedent_id"] == ccp_id, "P11 Ask cites the CCP ruling on interim leaders"
    )
    a = client.post("/api/ask", json={"question": "How do we settle CPI revisions?"}).json()
    check(not a["grounded"] and "Nothing in the governed record" in a["answer"], "P11 Ask says when nothing covers it")
    a = client.post("/api/ask", json={"question": "anything", "contract_id": "kalshi:KXG7LEADEROUT-27JAN20-DJT"}).json()
    check(a["grounded"] and a["citations"], "P11 Ask about a contract cites the precedents that bear on it")
    check("no model" in a["method"], "P11 answers are retrieved from the record, not generated")

    # P12 supersession retires the precedent
    svc = get_decisions(store)
    base = svc.get(ccp_id)
    replacement = svc.create(
        decision_type=base["decision_type"],
        question=base["question"],
        selection=base["selection"],
        rationale="Restated with the same holding.",
        actor="operator:gate",
        affected_case_ids=base["affected_case_ids"],
        cluster_id=base["cluster_id"],
        supersedes=ccp_id,
    )
    engine.refresh()
    check(engine.get(ccp_id)["state"] == "superseded", "P12 superseding a decision retires its precedent")
    check(engine.get(replacement["decision_id"])["state"] == "active", "P12 the superseding decision is the precedent")

    # P13 standing fine print
    fake = {
        "precedent_id": "fineprint",
        "contracts": [],
        "clauses": [{"text": "x", "normalized": P.normalize_clause("The fine print sentence 3.")}],
    }
    row = {"venue": "kalshi", "market_id": "Z", "event_id": "Z", "title": "t", "rules": "The fine print sentence 3."}
    hit = engine.match(row, precedents=[fake | {"selection": ""}], corpus=corpus)
    miss = engine.match(
        row,
        precedents=[fake | {"selection": ""}],
        corpus=corpus,
        template_sentences={P.normalize_clause("The fine print sentence 3.")},
    )
    check(
        hit and hit[0]["tier"] == "same_clause" and not miss,
        "P13 a clause that is standing fine print carries no ruling",
    )

    # P14 re-triage
    tri = vi.retriage(store, dry_run=True)
    closed_precedent = [c for c in tri["closed"] if "27JAN20" in c["subject"] or "28JAN20" in c["subject"]]
    check(not closed_precedent, "P14 re-triage never closes precedent-routed work")

    # P15 boundary
    before = store.summary()
    client.post("/api/ask", json={"question": "death in office"})
    client.post(
        "/api/appeals/check", json={"contract_id": "kalshi:KXG7LEADEROUT-26JUL20-DJT", "requested_selection": "x"}
    )
    client.get("/api/precedents")
    after = store.summary()
    keys = ("contracts", "authorities", "evidence_records", "resolution_runs")
    check(
        all(before.get(k) == after.get(k) for k in keys),
        "P15 precedent reads change no contract, evidence or resolution",
    )
    check(store.verify_audit_chain()["ok"], "P15 the audit chain verifies end to end")

    # P16 reads write nothing (precedent is materialized on write paths and at startup)
    with store.connect() as db:
        snap = lambda: (  # noqa: E731
            db.execute("SELECT COUNT(*) n FROM audit_events").fetchone()["n"],
            db.execute("SELECT COUNT(*) n, MAX(updated_at) m FROM precedents").fetchone()[:],
        )
        before_reads = snap()
    live_pattern = next((c for c in clusters(client) if c["count"] >= 1), None)
    client.get("/api/precedents")
    client.get("/api/precedents/match/kalshi:KXG7LEADEROUT-27JAN20-DJT")
    client.post("/api/ask", json={"question": "Do acting leaders count?"})
    if live_pattern:
        client.get(f"/api/decision-context/{live_pattern['cluster_id']}")
        client.post("/api/decisions/consistency", json={"cluster_id": live_pattern["cluster_id"], "selection": "x"})
    with store.connect() as db:
        after_reads = (
            db.execute("SELECT COUNT(*) n FROM audit_events").fetchone()["n"],
            db.execute("SELECT COUNT(*) n, MAX(updated_at) m FROM precedents").fetchone()[:],
        )
    check(before_reads == after_reads, "P16 read endpoints write nothing to precedent state or the audit chain")

    # P17 an overrule retires the whole line, however long
    ccp_cases = get_decisions(store).get(ccp_id)["affected_case_ids"]
    line = [
        engine.build(
            {
                "decision_id": f"dec_line_{n}",
                "decision_type": "policy_interpretation",
                "selection": "Acting leaders count once they chair a Politburo Standing Committee meeting",
                "affected_case_ids": ccp_cases,
                "created_at": f"2026-09-2{n}T00:00:00Z",
            }
        )["precedent_id"]
        for n in range(7)
    ]
    probe = dict(engine._contract_row("kalshi:KXXISUCCESSOR-45JAN01-LQIA"), contract_id="kalshi:PROBE-CCP")
    cons = engine.consistency(
        selection="Only a formal party announcement counts", rows=[probe], decision_type="policy_interpretation"
    )
    check(
        set(line) <= set(cons["peers"]) and len(cons["peer_matches"]) == len(cons["peers"]),
        f"P17 consistency returns every applicable peer, not a top-5 ({len(cons['peers'])} peers)",
    )
    retired = engine.overrule_line(line[0], cons["peer_matches"], by_decision="dec_gate", reason="gate", actor="gate")
    check(set(line) <= set(retired), f"P17 overruling one retires all {len(line)} holding the same ruling")
    check(
        engine.overrule_line(line[0], cons["peer_matches"], by_decision="dec_gate", reason="gate", actor="gate") == [],
        "P17 a repeated or concurrent overrule is a no-op, not an error",
    )
    print("PRECEDENT GATE: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
