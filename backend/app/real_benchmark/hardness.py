"""Deterministic hardness classifier for benchmark candidates.

Hand-picking hard cases does not scale. This module scores every candidate in a
collected pool into a v0.2 hardness class from signals available in bulk, so a
large pool from the collectors can be bucketed automatically and only the
borderline rows need a human.

Design principles (matching Arbiter's own):
- Deterministic and explainable. Every classification carries component scores
  and human-readable reasons. No model call, no randomness.
- Conservative. When no hard signal fires, a clean price threshold is
  `control_easy` and everything else is `unclassified` (routed to review), never
  force-fit into a hard class.
- The single-candidate classes only. `cross_venue_disagreement` needs two
  markets and stays in cross_venue.join_candidates; it is never assigned here.

Primary signals:
- disputed: Polymarket UMA dispute-round count (metadata.uma_dispute_count), or a
  venue clarification/disclaimer in the rules ("does not count", "clarification").
- interpretive_criteria: undefined qualitative terms in the resolution rules,
  and/or a vague resolution source ("consensus of credible reporting").
- revised_source: revision-prone series in the title/rules (CPI, payrolls, GDP).
- multi_source_conflict: an "official" named source in a domain where the official
  result is commonly contested (elections). Flagged for review, not auto-trusted.
- late_or_void: settled materially after close, or voided.
- control_easy: a clean price/number threshold with no hard signal.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Iterable

# Qualitative terms whose meaning the rules rarely pin down operationally.
INTERPRETIVE_TERMS = (
    "permanent", "permanently", "credible", "substantial", "substantially",
    "meaningful", "genuine", "consensus", "de facto", "effectively",
    "resolve amicably", "in good faith", "at the discretion", "good-faith",
)
# Deliberately excludes common template words (announce/official/major/widely/
# generally/successful): they ride on venue rules templates and do not
# discriminate hard from easy. Interpretive hardness often lives in an undefined
# common noun in the QUESTION ("suit", "recession"), which no lexicon catches --
# so interpretive is a REVIEW suggestion here, never an auto-trusted class.

# Phrases that hand resolution to judgment rather than a named authority.
VAGUE_SOURCE_MARKERS = (
    "consensus of credible reporting", "credible reporting", "credible sources",
    "credible media", "at the discretion", "sole discretion", "reasonably determine",
    "generally accepted", "a consensus of", "widely reported", "as determined by the market",
)

# Venue clarifications/disclaimers signal a contested interpretation.
DISCLAIMER_MARKERS = (
    "does not count", "will not count", "not count as", "for the avoidance of doubt",
    "clarification", "to clarify", "this does not include", "for clarity", "disclaimer",
)

# Revision-prone economic series.
REVISION_SERIES = (
    "cpi", "inflation", "ppi", "pce", "nonfarm", "non-farm", "payroll", "payrolls",
    "unemployment", "jobless", "gdp", "jobs report", "retail sales", "initial claims",
)

# Election domain, where an "official" result is commonly contested.
ELECTION_MARKERS = (
    "election", "presidential", "parliamentary", "won the", "win the", "winner of",
    "prime minister", "president of",
)

VOID_MARKERS = ("void", "voided", "canceled", "cancelled", "invalid", "no contest")

# A price/number threshold contract (the easy, deterministic kind).
_THRESHOLD_RE = re.compile(
    r"(target price|above \$?\d|below \$?\d|reach \$?\d|hit \$?\d|"
    r"\babove\b.*\d|\bbelow\b.*\d|greater than \$?\d|less than \$?\d|"
    r"\bat or above\b|\bat or below\b|increase by \d)",
    re.IGNORECASE,
)

# Priority when several classes fire. Strongest evidence of hardness first.
# interpretive_criteria is intentionally NOT here: it cannot be auto-assigned
# reliably from a lexicon (the hardness lives in undefined common nouns, and every
# venue/sport template carries its own filler). It is computed as an advisory
# `interpretive_hint` instead, to guide human triage of the unclassified pile.
# The genuinely interpretive cases that matter tend to also be `disputed`
# (objective UMA dispute count), which IS assigned.
PRIORITY = (
    "disputed",
    "multi_source_conflict",
    "revised_source",
    "late_or_void",
    "control_easy",
    "unclassified",
)


def _text(row: dict[str, Any]) -> str:
    return " ".join(str(row.get(k) or "") for k in ("title", "rules")).lower()


def _parse_dt(s: Any) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None


def _disputed(row: dict[str, Any], txt: str) -> tuple[float, list[str]]:
    reasons: list[str] = []
    score = 0.0
    meta = row.get("metadata") or {}
    n = meta.get("uma_dispute_count")
    if isinstance(n, int) and n > 0:
        score = min(1.0, 0.5 + 0.15 * n)
        reasons.append(f"UMA dispute rounds: {n}")
    hits = [m for m in DISCLAIMER_MARKERS if m in txt]
    if hits:
        score = max(score, 0.55)
        reasons.append("venue clarification/disclaimer: " + ", ".join(hits[:3]))
    return score, reasons


def _interpretive(row: dict[str, Any], txt: str, boilerplate: frozenset[str] = frozenset()) -> tuple[float, list[str]]:
    rules = str(row.get("rules") or "").lower()
    terms = sorted({t for t in INTERPRETIVE_TERMS if t in rules and t not in boilerplate})
    vague = [m for m in VAGUE_SOURCE_MARKERS if m in txt and m not in boilerplate]
    score = min(1.0, 0.22 * len(terms) + (0.5 if vague else 0.0))
    reasons: list[str] = []
    if terms:
        reasons.append("undefined qualitative terms: " + ", ".join(terms[:6]))
    if vague:
        reasons.append("vague resolution source: " + ", ".join(vague[:2]))
    return score, reasons


def _revised_source(row: dict[str, Any], txt: str) -> tuple[float, list[str]]:
    hits = sorted({s for s in REVISION_SERIES if s in txt})
    if not hits:
        return 0.0, []
    return 0.6, ["revision-prone series: " + ", ".join(hits[:4])]


def _multi_source(row: dict[str, Any], txt: str) -> tuple[float, list[str]]:
    is_election = any(m in txt for m in ELECTION_MARKERS)
    names_official = "official" in txt or "officially" in txt or "certified" in txt
    if is_election and names_official:
        return 0.5, ["election with an 'official'/'certified' source (official result commonly contested)"]
    if is_election:
        return 0.3, ["election market (official vs reported result may diverge)"]
    return 0.0, []


def _late_or_void(row: dict[str, Any], txt: str) -> tuple[float, list[str]]:
    reasons: list[str] = []
    score = 0.0
    # Only a genuinely non-binary/void OUTCOME counts; the word "void" appears in
    # templated conditional clauses on many easy markets and is not a signal.
    if str(row.get("known_outcome") or "").upper() in {"VOID", "CANCELED", "CANCELLED", ""}:
        if str(row.get("known_outcome") or "").upper() != "":
            score = 0.6
            reasons.append("void/canceled outcome")
    close = _parse_dt(row.get("closed_at"))
    settle = _parse_dt(row.get("settled_at"))
    if close and settle:
        gap_days = (settle - close).total_seconds() / 86400.0
        if gap_days > 3:
            score = max(score, min(1.0, 0.4 + 0.05 * gap_days))
            reasons.append(f"settled {gap_days:.1f} days after close")
    return score, reasons


def _control_easy(row: dict[str, Any], txt: str) -> tuple[float, list[str]]:
    if _THRESHOLD_RE.search(txt):
        return 0.5, ["clean price/number threshold"]
    return 0.0, []


_SCORERS = {
    "disputed": _disputed,
    "interpretive_criteria": _interpretive,
    "revised_source": _revised_source,
    "multi_source_conflict": _multi_source,
    "late_or_void": _late_or_void,
    "control_easy": _control_easy,
}

# A class only "fires" above its own threshold; below it the signal is noise.
_FIRE_THRESHOLD = {
    "disputed": 0.5,
    "multi_source_conflict": 0.3,
    "interpretive_criteria": 0.44,
    "revised_source": 0.5,
    "late_or_void": 0.4,
    "control_easy": 0.5,
}


def classify_candidate(row: dict[str, Any], boilerplate: frozenset[str] = frozenset()) -> dict[str, Any]:
    txt = _text(row)
    scores: dict[str, float] = {}
    reasons: dict[str, list[str]] = {}
    for cls, fn in _SCORERS.items():
        if cls == "interpretive_criteria":
            sc, rs = fn(row, txt, boilerplate)
        else:
            sc, rs = fn(row, txt)
        scores[cls] = round(sc, 3)
        if rs:
            reasons[cls] = rs

    fired = [c for c in PRIORITY if c in _SCORERS and scores.get(c, 0.0) >= _FIRE_THRESHOLD[c]]

    # control_easy only stands when no HARD class fired.
    hard_fired = [c for c in fired if c != "control_easy"]
    if hard_fired:
        primary = next(c for c in PRIORITY if c in hard_fired)
    elif "control_easy" in fired:
        primary = "control_easy"
    else:
        primary = "unclassified"

    interpretive_hint = scores.get("interpretive_criteria", 0.0) >= _FIRE_THRESHOLD["interpretive_criteria"]

    needs_review = (
        primary == "multi_source_conflict"
        or (primary == "disputed" and not (row.get("metadata") or {}).get("uma_dispute_count"))
        or (primary == "unclassified" and interpretive_hint)
    )

    return {
        "case_id": row.get("case_id"),
        "venue": row.get("venue"),
        "title": row.get("title"),
        "primary_class": primary,
        "hardness_score": round(max(scores.values(), default=0.0), 3),
        "fired_classes": hard_fired or (["control_easy"] if primary == "control_easy" else []),
        "interpretive_hint": interpretive_hint,
        "scores": scores,
        "reasons": reasons,
        "needs_review": needs_review,
    }


BOILERPLATE_DF = 0.35  # a term in >=35% of the pool is templated, not signal


def _boilerplate_for_group(group: list[dict[str, Any]]) -> frozenset[str]:
    n = len(group) or 1
    candidates = list(INTERPRETIVE_TERMS) + list(VAGUE_SOURCE_MARKERS)
    df: dict[str, int] = {t: 0 for t in candidates}
    for r in group:
        txt = _text(r)
        for t in candidates:
            if t in txt:
                df[t] += 1
    return frozenset(t for t, c in df.items() if c / n >= BOILERPLATE_DF)


def _compute_boilerplate(rows: list[dict[str, Any]]) -> dict[str, frozenset[str]]:
    """Boilerplate is venue-specific: each venue has its own rules template, so a
    term is templated relative to ITS venue, not the mixed pool. (Polymarket's
    'consensus of credible reporting' is ~universal on Polymarket but absent on
    Kalshi; a whole-pool threshold would dilute it below the cutoff.) Returns a
    per-venue set; a small venue group (< 10 rows) also inherits the global set so
    a thin sample still gets some protection."""
    by_venue: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        by_venue.setdefault(str(r.get("venue") or ""), []).append(r)
    global_set = _boilerplate_for_group(rows)
    out: dict[str, frozenset[str]] = {}
    for venue, group in by_venue.items():
        vset = _boilerplate_for_group(group)
        out[venue] = vset if len(group) >= 10 else (vset | global_set)
    return out


def classify_pool(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = list(rows)
    boilerplate_by_venue = _compute_boilerplate(rows)
    classified = [
        classify_candidate(r, boilerplate_by_venue.get(str(r.get("venue") or ""), frozenset()))
        for r in rows
    ]
    dist: dict[str, int] = {}
    by_class: dict[str, list[str]] = {}
    review = 0
    hints = 0
    for c in classified:
        dist[c["primary_class"]] = dist.get(c["primary_class"], 0) + 1
        by_class.setdefault(c["primary_class"], []).append(c["case_id"])
        if c["needs_review"]:
            review += 1
        if c.get("interpretive_hint"):
            hints += 1
    # Within each class, rank hardest first for curation.
    ranked = sorted(classified, key=lambda c: (-c["hardness_score"], str(c["primary_class"])))
    return {
        "classified": ranked,
        "summary": {
            "total": len(classified),
            "distribution": dict(sorted(dist.items(), key=lambda kv: -kv[1])),
            "needs_review": review,
            "interpretive_hints": hints,
            "boilerplate_terms_ignored": {v: sorted(t) for v, t in boilerplate_by_venue.items()},
            "note": "cross_venue_disagreement is not assigned here (needs the join). "
                    "unclassified rows are neither easy nor clearly hard -> human triage. "
                    "Terms in boilerplate_terms_ignored were templated across the pool and "
                    "carried no interpretive weight.",
        },
    }
