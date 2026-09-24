"""Tests for the cross-venue join. No network I/O; synthetic + real fixture."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.real_benchmark.cross_venue import (  # noqa: E402
    CandidateFingerprint,
    join_candidates,
    score_pair,
)


def _row(venue, cid, title, outcome, settled="2026-09-09T18:00:00Z"):
    return {"case_id": cid, "venue": venue, "title": title, "known_outcome": outcome, "settled_at": settled}


def test_same_event_disagreement_is_surfaced_and_ranked_first():
    rows = [
        _row("kalshi", "k1", "Bitcoin above 78,000 on September 9, 2PM ET?", "YES"),
        _row("polymarket", "p1", "Will Bitcoin be above $78,000 on Sep 9?", "NO"),
        _row("kalshi", "k2", "Ethereum above 2,520 on September 9?", "YES"),
        _row("polymarket", "p2", "Ethereum above 2,520 on September 9?", "YES"),
    ]
    res = join_candidates(rows, min_confidence=0.3)
    classes = [p["pair_class"] for p in res["pairs"]]
    assert "outcome_disagreement" in classes
    # disagreement ranks ahead of agreement
    assert res["pairs"][0]["pair_class"] == "outcome_disagreement"
    top = res["pairs"][0]
    assert {top["left"]["case_id"], top["right"]["case_id"]} == {"k1", "p1"}
    assert "78000" in top["evidence"]["shared_numbers"]


def test_unrelated_markets_do_not_match():
    rows = [
        _row("kalshi", "k1", "Will the Lakers win the NBA title?", "NO"),
        _row("polymarket", "p1", "Bitcoin above 78,000 on September 9?", "YES"),
    ]
    res = join_candidates(rows, min_confidence=0.35)
    assert res["summary"]["pair_count"] == 0


def test_shared_number_alone_does_not_clear_threshold():
    # Same threshold number, totally different events: prefilter lets them
    # through, but confidence must stay low enough to be filtered.
    a = CandidateFingerprint.from_row(_row("kalshi", "k", "Chiefs win by 7 points?", "YES"))
    b = CandidateFingerprint.from_row(_row("polymarket", "p", "CPI rises 7 percent?", "NO"))
    scored = score_pair(a, b)
    assert scored["confidence"] < 0.35


def test_agreement_pairs_kept_as_controls():
    rows = [
        _row("kalshi", "k", "Ethereum above 2,520 on September 9?", "YES"),
        _row("polymarket", "p", "Ethereum above 2,520 on September 9?", "YES"),
    ]
    res = join_candidates(rows, min_confidence=0.3)
    assert res["summary"]["by_class"].get("outcome_agreement") == 1


def test_real_fixture_runs_if_present():
    fixture = ROOT / "benchmarks" / "candidates_v0_1.jsonl"
    if not fixture.exists():
        return
    import json

    rows = [json.loads(l) for l in fixture.open()]
    res = join_candidates(rows, min_confidence=0.35)
    assert res["summary"]["left_count"] > 0
    assert res["summary"]["right_count"] > 0
    for p in res["pairs"]:
        assert p["requires_human_confirmation"] is True
        assert 0.0 <= p["match_confidence"] <= 1.0


if __name__ == "__main__":
    import traceback

    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS {fn.__name__}")
            passed += 1
        except Exception:
            print(f"FAIL {fn.__name__}")
            traceback.print_exc()
    print(f"\n{passed}/{len(fns)} passed")
    sys.exit(0 if passed == len(fns) else 1)
