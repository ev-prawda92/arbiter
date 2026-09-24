"""Tests for seed-driven targeted collection. Fetchers are injected, so no
network I/O runs here."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.real_benchmark.targeted import Seed, collect_targeted  # noqa: E402


def _mk(venue, ident, outcome):
    return {
        "case_id": f"{venue}-{ident}",
        "venue": venue,
        "external_market_id": ident,
        "title": f"{venue} market {ident}",
        "rules": "resolves according to the official source",
        "known_outcome": outcome,
        "settled_at": "2026-06-11T13:00:00Z",
    }


def test_seed_requires_id():
    try:
        Seed.from_row({"label": "no id"})
    except ValueError:
        return
    raise AssertionError("expected ValueError on missing seed_event_id")


def test_disagreement_seed_is_flagged():
    seeds = [
        {
            "seed_event_id": "cpi-may-2026",
            "label": "CPI May 2026 > 0.2%",
            "kalshi": ["KX1"],
            "polymarket": ["poly-1"],
        }
    ]
    store = {"KX1": _mk("kalshi", "KX1", "YES"), "poly-1": _mk("polymarket", "poly-1", "NO")}
    res = collect_targeted(
        seeds,
        fetch_kalshi=lambda i: store.get(i),
        fetch_polymarket=lambda i: store.get(i),
    )
    assert res["summary"]["dual_listed_seeds"] == 1
    assert res["summary"]["disagreement_seeds"] == 1
    assert "cpi-may-2026" in res["summary"]["disagreement_seed_ids"]
    for r in res["rows"]:
        assert r["seed_event_id"] == "cpi-may-2026"
        assert r["seed_label"] == "CPI May 2026 > 0.2%"


def test_agreement_seed_not_flagged():
    seeds = [{"seed_event_id": "s", "label": "x", "kalshi": ["KX1"], "polymarket": ["poly-1"]}]
    store = {"KX1": _mk("kalshi", "KX1", "YES"), "poly-1": _mk("polymarket", "poly-1", "YES")}
    res = collect_targeted(seeds, fetch_kalshi=lambda i: store.get(i), fetch_polymarket=lambda i: store.get(i))
    assert res["summary"]["dual_listed_seeds"] == 1
    assert res["summary"]["disagreement_seeds"] == 0


def test_missing_side_is_not_dual_and_records_miss():
    seeds = [{"seed_event_id": "s", "label": "x", "kalshi": ["KX1"], "polymarket": ["poly-missing"]}]
    store = {"KX1": _mk("kalshi", "KX1", "YES")}
    res = collect_targeted(seeds, fetch_kalshi=lambda i: store.get(i), fetch_polymarket=lambda i: store.get(i))
    cov = res["coverage"][0]
    assert cov["dual_listed"] is False
    assert any(e["identifier"] == "poly-missing" for e in cov["errors"])


def test_fetch_error_is_recorded_not_raised():
    def boom(_i):
        raise RuntimeError("HTTP 503")

    seeds = [{"seed_event_id": "s", "label": "x", "kalshi": ["KX1"], "polymarket": ["poly-1"]}]
    res = collect_targeted(seeds, fetch_kalshi=boom, fetch_polymarket=lambda i: _mk("polymarket", i, "NO"))
    cov = res["coverage"][0]
    assert any("503" in e["error"] for e in cov["errors"])
    assert cov["polymarket_resolved"] == 1


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
