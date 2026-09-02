"""Pre-listing contract intelligence for Arbiter v0.4.

This module never resolves a market. It converts deterministic engine flags into a
structured drafting review so an exchange can improve terms *before* listing.
"""

from __future__ import annotations

import re


def design_review(report: dict, criteria: str) -> dict:
    levers = report["levers"]
    deficiencies = []
    clauses = []

    for lever in ("source", "timing", "definition"):
        for flag in levers[lever]["flags"]:
            deficiencies.append({"lever": lever, "flag": flag, "severity": _severity(levers[lever]["score"])})

    src_flags = " ".join(levers["source"]["flags"]).lower()
    tim_flags = " ".join(levers["timing"]["flags"]).lower()
    def_flags = " ".join(levers["definition"]["flags"]).lower()

    if "authoritative source" in src_flags or "source not explicitly" in src_flags:
        clauses.append({
            "lever": "source",
            "title": "Designate a governing source",
            "text": "Designate one named authoritative resolution source and identify the exact publication, dataset, report, or endpoint that governs settlement.",
        })
    if "multiple sources" in src_flags:
        clauses.append({
            "lever": "source",
            "title": "Add source hierarchy",
            "text": "State which source controls if sources disagree, and name a fallback source that applies only if the primary source is unavailable.",
        })
    if "revision" in src_flags or "revision" in tim_flags:
        clauses.append({
            "lever": "timing",
            "title": "Freeze the revision rule",
            "text": "State whether Arbiter uses the initial published value or a later revised value, and define the revision window after which the observation is final.",
        })
    if "time" in tim_flags or "timezone" in tim_flags or "date-only" in tim_flags:
        clauses.append({
            "lever": "timing",
            "title": "Specify the settlement clock",
            "text": "Specify an exact observation date, clock time, and timezone. If the market is calendar-day based, explicitly state that no intraday snapshot is required.",
        })
    if "reversible event" in tim_flags:
        clauses.append({
            "lever": "timing",
            "title": "Add persistence / snapshot logic",
            "text": "For reversible events, define the precise snapshot or minimum continuous duration required for the condition to count as satisfied.",
        })
    if "interpretive term" in def_flags:
        clauses.append({
            "lever": "definition",
            "title": "Define interpretive terms",
            "text": "Replace interpretive language with observable conditions, named actors, required actions, and objective evidence that jointly constitute satisfaction.",
        })
    if "no numeric" in def_flags:
        clauses.append({
            "lever": "definition",
            "title": "Add an objective test",
            "text": "Define a binary, externally verifiable test for YES versus NO. Use measurable thresholds or enumerated factual conditions where possible.",
        })
    if "inclusive" in def_flags:
        clauses.append({
            "lever": "definition",
            "title": "Clarify boundary conditions",
            "text": "State whether the threshold is inclusive or exclusive (for example, ‘at or above’ versus ‘above’).",
        })
    if "compound condition" in def_flags:
        clauses.append({
            "lever": "definition",
            "title": "Enumerate compound conditions",
            "text": "Number each required condition and state whether all conditions, any condition, or a specified subset must be satisfied.",
        })

    clauses = _dedupe(clauses)
    readiness = max(0, 100 - int(report["composite"]))
    status = "listing-ready" if report["verdict"]["key"] == "clean" else (
        "revise-before-listing" if report["verdict"]["key"] == "review" else "review-recommended"
    )

    return {
        "status": status,
        "readiness_score": readiness,
        "deficiencies": deficiencies,
        "recommended_clauses": clauses,
        "drafting_fix": _draft_fix(criteria, clauses),
        "principle": "AI and heuristics may identify and explain ambiguity; only governed deterministic rules determine resolution readiness.",
    }


def _draft_fix(criteria: str, clauses: list[dict]) -> str:
    base = re.sub(r"\s+", " ", (criteria or "").strip())
    if not clauses:
        return base
    additions = " ".join(f"[{c['title']}] {c['text']}" for c in clauses)
    return (base + "\n\nArbiter drafting additions:\n" + additions).strip()


def _severity(score: int) -> str:
    if score > 50:
        return "high"
    if score > 20:
        return "medium"
    return "low"


def _dedupe(items: list[dict]) -> list[dict]:
    seen = set()
    out = []
    for item in items:
        key = item["title"]
        if key not in seen:
            out.append(item)
            seen.add(key)
    return out
