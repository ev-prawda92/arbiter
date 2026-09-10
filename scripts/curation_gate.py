#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.real_benchmark.curation import curate_candidates, score_candidate


def check(name: str, cond: bool) -> None:
    if not cond:
        raise AssertionError(name)
    print(f"[PASS] {name}")


def candidate(case_id: str, title: str, rules: str, **extra):
    row = {
        "case_id": case_id,
        "venue": "kalshi",
        "external_market_id": case_id,
        "title": title,
        "rules": rules,
        "known_outcome": "YES",
        "source_url": "https://kalshi.com/example",
        "collected_at": "2026-09-09T00:00:00Z",
        "raw_sha256": "sha256:" + "a" * 64,
        "closed_at": "2026-09-08T20:00:00Z",
        "settled_at": "2026-09-08T21:00:00Z",
        "resolution_source": "https://bls.gov/example",
        "benchmark_evidence": {
            "observed_value": 3.1,
            "unit": "%",
            "authority": "BLS",
            "source_url": "https://bls.gov/example",
            "retrieved_at": "2026-09-08T21:00:00Z",
            "raw_sha256": "sha256:" + "b" * 64,
        },
    }
    row.update(extra)
    return row


def main() -> None:
    good = candidate(
        "good-1",
        "Will CPI be at least 3.0%?",
        "This market resolves YES if the official BLS CPI release reports year-over-year CPI at or above 3.0% for the specified month. Resolution is determined according to the official BLS source after publication at 08:30 ET.",
    )
    scored = score_candidate(good)
    check("benchmark-quality case scores >=80", scored.score >= 80)
    check("domain classification works", scored.category == "economics")

    bad = candidate(
        "bad-1",
        "Example market",
        "Trademark notice. This site is not affiliated with Example. All rights reserved.",
        resolution_source=None,
        benchmark_evidence=None,
        closed_at=None,
        settled_at=None,
    )
    bad_score = score_candidate(bad)
    check("boilerplate case rejected", not bad_score.accepted)
    check("boilerplate reason surfaced", "boilerplate_or_template_rules" in bad_score.rejection_reasons)

    duplicate = dict(good)
    duplicate["case_id"] = "good-2"
    duplicate["external_market_id"] = "good-2"
    duplicate["raw_sha256"] = "sha256:" + "c" * 64
    curated = curate_candidates([good, duplicate], min_score=80)
    check("duplicate title removed", curated["accepted_count"] == 1)
    check("duplicate rejection surfaced", curated["rejection_reasons"].get("duplicate_or_near_duplicate") == 1)

    print("CURATION GATE: PASS")


if __name__ == "__main__":
    main()
