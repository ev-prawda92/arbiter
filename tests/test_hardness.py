"""Tests for the hardness classifier, using rows modeled on the REAL cases
verified live on 2026-09-20 (Zelenskyy, Venezuela, CPI, Iran) plus a strike
ladder. No network."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.real_benchmark.hardness import classify_candidate, classify_pool  # noqa: E402

ZELENSKYY = {
    "case_id": "polymarket-546814", "venue": "polymarket",
    "title": "Will Zelenskyy wear a suit before July?",
    "rules": ("This market will resolve to Yes if Volodymyr Zelenskyy is photographed or "
              "videotaped wearing a suit between May 22 and June 30, 2025. The resolution "
              "source will be a consensus of credible reporting."),
    "known_outcome": "NO", "closed_at": "2025-06-30T12:00:00Z", "settled_at": "2025-07-09T00:30:39Z",
    "metadata": {"uma_dispute_count": 5},
}
CPI = {
    "case_id": "polymarket-527838", "venue": "polymarket",
    "title": "Will monthly inflation increase by 0.1% or less in March?",
    "rules": "Resolves Yes if the BLS CPI monthly change for March is 0.1% or less.",
    "known_outcome": "YES", "closed_at": "2025-04-10T12:00:00Z", "settled_at": "2025-04-10T16:27:17Z",
    "metadata": {"uma_dispute_count": 0},
}
VENEZUELA = {
    "case_id": "polymarket-502006", "venue": "polymarket",
    "title": "Will Edmundo Gonzalez win the 2024 Venezuela presidential election?",
    "rules": "Resolves Yes if Edmundo Gonzalez is the official winner of the 2024 Venezuela presidential election.",
    "known_outcome": "YES", "closed_at": "2024-08-01T12:00:00Z", "settled_at": "2024-08-06T18:37:36Z",
    "metadata": {"uma_dispute_count": 0},
}
STRIKE = {
    "case_id": "kalshi-KXETH", "venue": "kalshi",
    "title": "Ethereum above 2,520 on September 9?",
    "rules": "Resolves Yes if the ETH price is above 2520 at the target time according to the reference index.",
    "known_outcome": "NO", "closed_at": "2026-09-09T18:00:00Z", "settled_at": "2026-09-09T18:05:00Z",
    "metadata": {},
}
IRAN_KALSHI = {
    "case_id": "kalshi-KXUSAIRANAGREEMENT-27-26AUG", "venue": "kalshi",
    "title": "Will the US agree to a new Iranian nuclear deal before August?",
    "rules": ("Resolves Yes if the US officially agrees to a new Iranian nuclear deal. For the "
              "avoidance of doubt, a memorandum of understanding does not count as a deal."),
    "known_outcome": "NO", "closed_at": "2026-08-01T14:00:00Z", "settled_at": "2026-08-01T14:00:00Z",
    "metadata": {},
}


def test_zelenskyy_is_disputed_dispute_count_wins():
    c = classify_candidate(ZELENSKYY)
    assert c["primary_class"] == "disputed", c
    assert c["scores"]["disputed"] >= 0.5
    assert c["interpretive_hint"] is True  # advisory: also reads interpretive
    assert c["needs_review"] is False  # objective dispute count, no review needed


def test_iran_disclaimer_flags_disputed_for_review():
    c = classify_candidate(IRAN_KALSHI)
    assert c["primary_class"] == "disputed"
    assert c["needs_review"] is True  # lexical disclaimer, no dispute count -> review


def test_cpi_is_revised_source():
    c = classify_candidate(CPI)
    assert c["primary_class"] == "revised_source", c


def test_venezuela_is_multi_source_conflict():
    c = classify_candidate(VENEZUELA)
    assert c["primary_class"] == "multi_source_conflict", c
    assert c["needs_review"] is True


def test_strike_ladder_is_control_easy():
    c = classify_candidate(STRIKE)
    assert c["primary_class"] == "control_easy", c


def test_interpretive_is_hint_not_primary():
    row = {
        "case_id": "kalshi-cricket", "venue": "kalshi",
        "title": "Metro Bank One Day Cup Women: Essex vs Yorkshire",
        "rules": "A permanent result is required; matches abandoned permanently resolve per standings.",
        "known_outcome": "NO", "closed_at": "2026-09-09T12:00:00Z", "settled_at": "2026-09-09T15:00:00Z",
        "metadata": {},
    }
    c = classify_candidate(row)
    assert c["primary_class"] != "interpretive_criteria"  # never auto-assigned
    assert c["primary_class"] == "unclassified"
    assert c["interpretive_hint"] is True
    assert c["needs_review"] is True  # unclassified + hint -> triage


def test_pool_distribution():
    res = classify_pool([ZELENSKYY, CPI, VENEZUELA, STRIKE, IRAN_KALSHI])
    d = res["summary"]["distribution"]
    assert d.get("disputed") == 2
    assert d.get("revised_source") == 1
    assert d.get("multi_source_conflict") == 1
    assert d.get("control_easy") == 1
    assert res["summary"]["needs_review"] >= 2


if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        try:
            fn(); print(f"PASS {fn.__name__}"); passed += 1
        except Exception:
            print(f"FAIL {fn.__name__}"); traceback.print_exc()
    print(f"\n{passed}/{len(fns)} passed")
    sys.exit(0 if passed == len(fns) else 1)
