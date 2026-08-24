"""
Platform monitoring — the read-only intelligence layer.

Hard boundary: this module OBSERVES and REPORTS. It never feeds back into how any
individual contract resolves. Per-contract resolution stays deterministic and
evidence-bound (engine.py); this is the slow, human-facing meta view that tells the
exchange's own team where disputes cluster, which templates are weak, and where
coverage is thin. What they do about it is their call.
"""

from collections import defaultdict


def summarize(reports):
    counts = {"clean": 0, "monitored": 0, "review": 0}
    notional = {"clean": 0, "monitored": 0, "review": 0}
    total_notional = 0
    for r in reports:
        k = r["verdict"]["key"]
        counts[k] += 1
        notional[k] += r.get("open_interest", 0)
        total_notional += r.get("open_interest", 0)
    return {
        "reviewed": len(reports),
        "counts": counts,
        "notional": notional,
        "total_notional": total_notional,
        "held_notional": notional["review"],
        "clean_rate": _pct(counts["clean"], len(reports)),
    }


def by_category(reports):
    """Where does dispute risk concentrate? Highest avg composite = weakest templates."""
    buckets = defaultdict(list)
    for r in reports:
        buckets[r["category"]].append(r)
    rows = []
    for cat, items in buckets.items():
        review = sum(1 for i in items if i["verdict"]["key"] == "review")
        avg = round(sum(i["composite"] for i in items) / len(items), 1)
        held_notional = sum(i.get("open_interest", 0) for i in items if i["verdict"]["key"] == "review")
        rows.append({
            "category": cat,
            "count": len(items),
            "avg_composite": avg,
            "review_count": review,
            "review_rate": _pct(review, len(items)),
            "held_notional": held_notional,
        })
    rows.sort(key=lambda x: x["avg_composite"], reverse=True)
    return rows


def lever_pressure(reports):
    """Which lever drives the most risk platform-wide? Points at what to fix first."""
    tot = {"source": 0, "timing": 0, "definition": 0}
    for r in reports:
        for k in tot:
            tot[k] += r["levers"][k]["score"]
    n = max(1, len(reports))
    avgs = {k: round(v / n, 1) for k, v in tot.items()}
    worst = max(avgs, key=avgs.get)
    return {"averages": avgs, "primary_driver": worst}


def coverage_gaps(reports, threshold=50):
    """Categories where the review rate is high enough to need stricter guidance."""
    gaps = []
    for row in by_category(reports):
        if row["review_rate"] >= threshold:
            gaps.append({
                "category": row["category"],
                "review_rate": row["review_rate"],
                "recommendation": "Tighten the contract template for this category: "
                                  "designate a source, add an explicit settlement clock, "
                                  "and define interpretive terms before listing.",
            })
    return gaps


def _pct(a, b):
    return round(100 * a / b) if b else 0
