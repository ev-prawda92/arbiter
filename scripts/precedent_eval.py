#!/usr/bin/env python3
"""Measure precedent matching on real venue markets.

Data: the two recorded live scans in tests/fixtures (Kalshi + Polymarket,
Sep 23-24 2026; 838 distinct open markets after de-duplication).

1. Template transfer across events. A ruling on one event should reach the
   next event of the same kind. Ground truth is the template family: the
   Kalshi series ticker with period digits collapsed (KXNCAAF2QTOTAL and
   KXNCAAF3QTOTAL are one family), or for Polymarket the normalized title
   shape. For every market whose family appears in 2+ events, its own event is
   hidden and we ask: is the best-matching contract from another event in the
   same family, and does it clear the same-template threshold?

2. False applicability. For markets whose family appears in only one event
   there is no true cross-event precedent; any match at or above the
   threshold is counted and listed so a reviewer can judge it.

3. Clause reach. For each market the classifier flags, the clauses a ruling
   would be about are matched against every other event's markets.

Usage:  python3 scripts/precedent_eval.py [--json]
"""

from __future__ import annotations

import argparse
import collections
import gzip
import json
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "backend"))

from app import precedents as P  # noqa: E402
from app import venue_intake as vi  # noqa: E402

SCANS = ("venue_scan_2026-09-23.json.gz", "venue_scan_2026-09-24.json.gz")


def load_rows() -> list[dict]:
    rows, seen = [], set()
    for name in SCANS:
        with gzip.open(os.path.join(ROOT, "tests", "fixtures", name), "rt") as fh:
            for m in json.load(fh)["markets"]:
                r = vi.normalize(m["venue"], m["raw"], m["url"])
                key = (r["venue"], r["market_id"])
                if key in seen or not r["rules"]:
                    continue
                seen.add(key)
                r["contract_id"] = f"{r['venue']}:{r['market_id']}"
                rows.append(r)
    return rows


def family(r: dict) -> str:
    if r["venue"] == "kalshi":
        return "k:" + re.sub(r"\d", "", P.series_of(r))
    return "p:" + re.sub(r"<n>|[-+()%°$]", "", P.normalize_clause(r["title"])).strip()


def evaluate() -> dict:
    rows = load_rows()
    corpus = P.Corpus(rows)
    vecs = [corpus.vectors(r) for r in rows]
    fam = [family(r) for r in rows]
    events_of: dict[str, set] = collections.defaultdict(set)
    for f, r in zip(fam, rows):
        events_of[f].add(r["event_id"])

    def best_other_event(i: int) -> tuple[float, int]:
        return max(
            (corpus.similarity(vecs[i], vecs[j]), j)
            for j in range(len(rows))
            if rows[j]["event_id"] != rows[i]["event_id"]
        )

    pos = [i for i in range(len(rows)) if len(events_of[fam[i]]) >= 2]
    neg = [i for i in range(len(rows)) if len(events_of[fam[i]]) < 2]
    pos_res = [(*best_other_event(i), i) for i in pos]
    neg_res = [(*best_other_event(i), i) for i in neg]

    thresholds = {}
    for th in (0.60, 0.70, 0.75, P.SAME_TEMPLATE, 0.85, 0.90):
        reached = [(s, j, i) for s, j, i in pos_res if s >= th]
        correct = sum(fam[j] == fam[i] for _, j, i in reached)
        thresholds[f"{th:.2f}"] = {
            "recall": round(len(reached) / len(pos), 3),
            "reached": len(reached),
            "precision": round(correct / len(reached), 3) if reached else None,
            "correct": correct,
            "no_family_over_threshold": sum(s >= th for s, _, _ in neg_res),
        }
    top1_wrong = [
        {"score": round(s, 3), "market": rows[i]["title"][:70], "matched": rows[j]["title"][:70]}
        for s, j, i in pos_res
        if fam[j] != fam[i]
    ]
    false_applies = [
        {
            "score": round(s, 3),
            "market": f"{rows[i]['contract_id']}: {rows[i]['title'][:60]}",
            "matched": f"{rows[j]['contract_id']}: {rows[j]['title'][:60]}",
        }
        for s, j, i in sorted(neg_res, reverse=True)
        if s >= P.SAME_TEMPLATE
    ]

    # 3. clause reach of flagged markets into other events
    bp = vi.boilerplate_for(rows)
    flagged = []
    for r in rows:
        klass = vi.review_class(vi.classify(r, bp), None, r, bp)
        if klass:
            flagged.append((r, klass))
    reach = []
    by_event: dict[str, list] = collections.defaultdict(list)
    for r, klass in flagged:
        by_event[r["event_id"]].append((r, klass))
    for event, members in by_event.items():
        r, klass = members[0]
        precedent = {
            "precedent_id": f"eval:{event}",
            "contracts": [dict(m, series=P.series_of(m)) for m, _ in members],
            "clauses": P.issue_clauses(r, klass),
        }
        templates = bp.get(vi.SENTENCE_KEY.format(venue=r["venue"]), frozenset())
        hits = []
        engine_like = P.PrecedentEngine.__new__(P.PrecedentEngine)
        for other in rows:
            if other["event_id"] == event:
                continue
            m = P.PrecedentEngine.match(
                engine_like,
                other,
                precedents=[precedent | {"selection": "", "decision_type": "policy_interpretation"}],
                corpus=corpus,
                template_sentences=templates,
                min_tier="same_template",
            )
            if m:
                hits.append(
                    {
                        "contract": other["contract_id"],
                        "title": other["title"][:60],
                        "tier": m[0]["tier"],
                        "score": m[0]["score"],
                        "clause": (m[0]["matched_clause"] or {}).get("contract_clause", "")[:90],
                    }
                )
        reach.append(
            {
                "event": event,
                "markets": len(members),
                "review_class": klass,
                "clauses": len(precedent["clauses"]),
                "applies_elsewhere": hits,
            }
        )

    return {
        "markets": len(rows),
        "families_multi_event": sum(len(e) >= 2 for e in events_of.values()),
        "positives": len(pos),
        "negatives": len(neg),
        "same_template_threshold": P.SAME_TEMPLATE,
        "thresholds": thresholds,
        "top1_wrong_family": top1_wrong,
        "no_family_matches_at_threshold": false_applies,
        "flagged_events": len(by_event),
        "clause_reach": reach,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    res = evaluate()
    if args.json:
        print(json.dumps(res, indent=2))
        return 0
    print(f"Precedent matching on {res['markets']} real markets ({res['families_multi_event']} template families")
    print(
        f"span 2+ events: {res['positives']} markets with a true cross-event precedent, {res['negatives']} without)\n"
    )
    print("threshold  recall            precision        no-family markets over threshold")
    for th, t in res["thresholds"].items():
        mark = "  <- same_template" if float(th) == res["same_template_threshold"] else ""
        print(
            f"  {th}     {t['reached']:>3}/{res['positives']} = {t['recall']:.3f}   "
            f"{t['correct']:>3}/{t['reached']:<3} = {t['precision']}   {t['no_family_over_threshold']}{mark}"
        )
    print(f"\nwrong top-1 family at any score: {len(res['top1_wrong_family'])}")
    print("no-family markets at or above same_template (review these):")
    for f in res["no_family_matches_at_threshold"]:
        print(f"  {f['score']:.2f}  {f['market']}\n        ~ {f['matched']}")
    print(f"\nclause reach: {res['flagged_events']} flagged events")
    for r in res["clause_reach"]:
        print(
            f"  {r['event']:<34} {r['markets']:>2} mkts {r['review_class']:<22} applies elsewhere: {len(r['applies_elsewhere'])}"
        )
        for h in r["applies_elsewhere"][:3]:
            print(f"      {h['tier']:<13} {h['score']:.2f} {h['contract']} {h['title']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
