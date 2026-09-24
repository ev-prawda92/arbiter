"""Targeted, seed-driven collection of dual-listed events across venues.

Bulk collection cannot produce cross-venue disagreement cases: the two venues
seldom list the same events in the same settled-page window. This module takes a
*seed list* of real-world questions, each naming the market identifiers it was
listed under at each venue, fetches those specific markets, normalizes them into
the standard candidate schema, tags them with their seed, and reports coverage:
which seeds resolved on both venues, and which of those disagree.

A seed row (JSONL) looks like:

    {
      "seed_event_id": "cpi-may-2026-mom",
      "label": "US CPI-U month-over-month for May 2026 above 0.2%",
      "kalshi": ["KXCPIYOY-26MAY-..."],
      "polymarket": ["will-cpi-...", "512345"],
      "notes": "BLS release 2026-06-11; both venues named the BLS print"
    }

Identifiers are lists so a single question that was split into several related
markets can be pulled together. Fetching is the only step here that needs the
network; the join and coverage report are pure functions over fetched rows.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from .cross_venue import join_candidates

FetchFn = Callable[[str], dict[str, Any] | None]


@dataclass
class Seed:
    seed_event_id: str
    label: str
    kalshi: list[str] = field(default_factory=list)
    polymarket: list[str] = field(default_factory=list)
    notes: str = ""

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "Seed":
        sid = str(row.get("seed_event_id") or "").strip()
        if not sid:
            raise ValueError("seed row missing seed_event_id")
        return cls(
            seed_event_id=sid,
            label=str(row.get("label") or "").strip(),
            kalshi=[str(x).strip() for x in (row.get("kalshi") or []) if str(x).strip()],
            polymarket=[str(x).strip() for x in (row.get("polymarket") or []) if str(x).strip()],
            notes=str(row.get("notes") or ""),
        )


def collect_targeted(
    seeds: Iterable[dict[str, Any]],
    *,
    fetch_kalshi: FetchFn,
    fetch_polymarket: FetchFn,
) -> dict[str, Any]:
    """Fetch every identifier in every seed, tag rows with their seed, and
    report per-seed coverage. `fetch_*` are injected so this is testable without
    network and so the caller controls rate limiting and error policy.

    A fetcher returning None (missing market, non-binary, unresolved) is recorded
    as a miss, not an error. A fetcher raising is recorded as an error against
    that identifier and does not abort the run.
    """
    rows: list[dict[str, Any]] = []
    coverage: list[dict[str, Any]] = []

    for raw in seeds:
        seed = Seed.from_row(raw)
        seed_rows: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []

        for venue, ids, fetch in (
            ("kalshi", seed.kalshi, fetch_kalshi),
            ("polymarket", seed.polymarket, fetch_polymarket),
        ):
            for ident in ids:
                try:
                    row = fetch(ident)
                except Exception as exc:  # noqa: BLE001 - recorded, not raised
                    errors.append({"venue": venue, "identifier": ident, "error": str(exc)[:200]})
                    continue
                if row is None:
                    errors.append({"venue": venue, "identifier": ident, "error": "no resolved binary market"})
                    continue
                row = dict(row)
                row["seed_event_id"] = seed.seed_event_id
                row["seed_label"] = seed.label
                seed_rows.append(row)
                rows.append(row)

        k_outcomes = sorted({r["known_outcome"] for r in seed_rows if r["venue"] == "kalshi"})
        p_outcomes = sorted({r["known_outcome"] for r in seed_rows if r["venue"] == "polymarket"})
        dual = bool(k_outcomes) and bool(p_outcomes)
        disagree = dual and set(k_outcomes) != set(p_outcomes)
        coverage.append(
            {
                "seed_event_id": seed.seed_event_id,
                "label": seed.label,
                "kalshi_resolved": len([r for r in seed_rows if r["venue"] == "kalshi"]),
                "polymarket_resolved": len([r for r in seed_rows if r["venue"] == "polymarket"]),
                "kalshi_outcomes": k_outcomes,
                "polymarket_outcomes": p_outcomes,
                "dual_listed": dual,
                "outcome_disagreement": disagree,
                "errors": errors,
            }
        )

    # Run the fuzzy join too, but confined within each seed group, so it can
    # corroborate the seed's own dual-listing claim with shared anchors.
    per_seed_pairs: list[dict[str, Any]] = []
    by_seed: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        by_seed.setdefault(r["seed_event_id"], []).append(r)
    for sid, group in by_seed.items():
        res = join_candidates(group, min_confidence=0.0)  # keep all within-seed pairs
        for p in res["pairs"]:
            p["seed_event_id"] = sid
            per_seed_pairs.append(p)

    dual_seeds = [c for c in coverage if c["dual_listed"]]
    disagreement_seeds = [c for c in coverage if c["outcome_disagreement"]]
    return {
        "rows": rows,
        "coverage": coverage,
        "within_seed_pairs": per_seed_pairs,
        "summary": {
            "seed_count": len(coverage),
            "rows_collected": len(rows),
            "dual_listed_seeds": len(dual_seeds),
            "disagreement_seeds": len(disagreement_seeds),
            "disagreement_seed_ids": [c["seed_event_id"] for c in disagreement_seeds],
            "note": "dual_listed / disagreement are provisional: a curator still confirms the two markets ask the same question before freezing.",
        },
    }
