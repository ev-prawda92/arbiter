"""Cross-venue join: surface Kalshi/Polymarket candidate pairs that plausibly
refer to the same real-world event, and flag where their resolved outcomes
disagree.

This is a *candidate surfacing* tool, matching this package's stance that
collection is not curation. The join never asserts that two markets are the
same event. It emits a match confidence, the anchors the two titles share, and
a class, and it marks every pair `requires_human_confirmation: true`. A human
curator confirms or rejects each pair before it enters a frozen holdout.

The highest-value output is the `outcome_disagreement` class: the same event
listed at two regulated venues that resolved to different YES/NO outcomes. At
most one venue can be right, so a confirmed disagreement pair is a benchmark
case whose correct answer can be argued from the contract text and evidence,
without appealing to Arbiter's own judgment.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable

# Words that carry no matching signal in market titles. Deliberately small:
# over-stripping loses anchors. Venue phrasing verbs (will/be) are dropped
# because they appear in nearly every title.
_STOPWORDS = frozenset(
    """a an the of to in on at for and or vs versus be will would does did is are was
    yes no this that by with from as it its than then over under above below between
    who what when which whether during into out up down more less least most any""".split()
)

_MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "sept": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}

# Kalshi strike-ladder titles are comma-joined bundles prefixed with the
# outcome word, e.g. "yes Target Price: $2.5997,no Target Price: $1,271.85".
# These prefixes are noise for event matching.
_STRIKE_PREFIX = re.compile(r"\b(yes|no)\s+target price:\s*", re.IGNORECASE)


def _tokens(text: str) -> list[str]:
    text = _STRIKE_PREFIX.sub(" ", text or "")
    text = text.lower()
    text = re.sub(r"[^a-z0-9$.,%\- ]+", " ", text)
    raw = [t.strip(".,-") for t in text.split()]
    return [t for t in raw if t and t not in _STOPWORDS and len(t) > 1]


def _numbers(text: str) -> set[str]:
    """Numeric anchors: thresholds, prices, counts. Commas stripped so
    78,600.77 and 78600.77 match; trailing .0 normalized."""
    out: set[str] = set()
    for m in re.findall(r"\$?\d[\d,]*\.?\d*%?", text or ""):
        cleaned = m.replace("$", "").replace(",", "").rstrip("%")
        if not cleaned or cleaned == ".":
            continue
        try:
            val = float(cleaned)
        except ValueError:
            continue
        # normalize integers vs floats: 2520 == 2520.0
        out.add(str(int(val)) if val.is_integer() else str(val))
    return out


def _dates(text: str) -> set[str]:
    """ISO and 'Month DD' style date anchors, normalized to MM-DD (year-free,
    because the two venues often phrase the same expiry with/without a year)."""
    out: set[str] = set()
    low = (text or "").lower()
    for m in re.finditer(r"(\d{4})-(\d{2})-(\d{2})", low):
        out.add(f"{int(m.group(2)):02d}-{int(m.group(3)):02d}")
    for name, mm in _MONTHS.items():
        for m in re.finditer(rf"\b{name}\.?\s+(\d{{1,2}})\b", low):
            out.add(f"{mm:02d}-{int(m.group(1)):02d}")
    return out


def _entities(tokens: list[str]) -> set[str]:
    """Content tokens that are not pure numbers — the lexical anchors
    (team names, tickers, people, places)."""
    return {t for t in tokens if not re.fullmatch(r"\$?\d[\d,]*\.?\d*%?", t)}


@dataclass(frozen=True)
class CandidateFingerprint:
    case_id: str
    venue: str
    title: str
    known_outcome: str
    settled_at: str | None
    tokens: tuple[str, ...]
    entities: frozenset[str]
    numbers: frozenset[str]
    dates: frozenset[str]

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "CandidateFingerprint":
        title = str(row.get("title") or "")
        toks = _tokens(title)
        return cls(
            case_id=str(row.get("case_id") or ""),
            venue=str(row.get("venue") or ""),
            title=title,
            known_outcome=str(row.get("known_outcome") or "").upper(),
            settled_at=row.get("settled_at") or row.get("closed_at"),
            tokens=tuple(toks),
            entities=frozenset(_entities(toks)),
            numbers=frozenset(_numbers(title)),
            dates=frozenset(_dates(title)),
        )


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a and not b:
        return 0.0
    union = a | b
    return len(a & b) / len(union) if union else 0.0


def _settle_gap_days(a: str | None, b: str | None) -> float | None:
    def parse(s: str | None) -> datetime | None:
        if not s:
            return None
        try:
            return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        except ValueError:
            return None

    da, db = parse(a), parse(b)
    if da is None or db is None:
        return None
    return abs((da - db).total_seconds()) / 86400.0


def score_pair(a: CandidateFingerprint, b: CandidateFingerprint) -> dict[str, Any]:
    """Confidence that a and b describe the same event, plus the shared anchors
    that justify it. Confidence is a weighted blend, not a probability."""
    ent = _jaccard(a.entities, b.entities)
    shared_numbers = a.numbers & b.numbers
    shared_dates = a.dates & b.dates
    shared_entities = a.entities & b.entities

    # Entity overlap is the backbone. Shared numeric/date anchors are strong
    # corroboration because they rarely coincide by chance across venues.
    num_bonus = 0.25 if shared_numbers else 0.0
    date_bonus = 0.15 if shared_dates else 0.0
    # A shared distinctive entity (len>=4) lifts terse titles that score low on
    # Jaccard alone.
    distinctive = any(len(e) >= 4 for e in shared_entities)
    ent_bonus = 0.10 if distinctive else 0.0

    confidence = min(1.0, 0.6 * ent + num_bonus + date_bonus + ent_bonus)
    return {
        "confidence": round(confidence, 4),
        "entity_jaccard": round(ent, 4),
        "shared_entities": sorted(shared_entities),
        "shared_numbers": sorted(shared_numbers),
        "shared_dates": sorted(shared_dates),
        "settle_gap_days": _settle_gap_days(a.settled_at, b.settled_at),
    }


def classify_pair(a: CandidateFingerprint, b: CandidateFingerprint) -> str:
    ao, bo = a.known_outcome, b.known_outcome
    binary = {"YES", "NO"}
    if ao in binary and bo in binary:
        return "outcome_disagreement" if ao != bo else "outcome_agreement"
    return "resolution_asymmetry"


def join_candidates(
    rows: Iterable[dict[str, Any]],
    *,
    min_confidence: float = 0.35,
    left_venue: str = "kalshi",
    right_venue: str = "polymarket",
) -> dict[str, Any]:
    """Return ranked cross-venue pairs above ``min_confidence``.

    Pairs are ordered so the curation-worthy ones come first: disagreements
    before agreements, then by descending confidence. Every pair is marked
    ``requires_human_confirmation``. This function performs no network I/O; it
    joins already-collected candidate rows.
    """
    fps = [CandidateFingerprint.from_row(r) for r in rows]
    left = [f for f in fps if f.venue == left_venue and f.tokens]
    right = [f for f in fps if f.venue == right_venue and f.tokens]

    pairs: list[dict[str, Any]] = []
    for a in left:
        for b in right:
            # Cheap prefilter: require at least one shared anchor of any kind,
            # else the O(n*m) scan does real work on hopeless pairs.
            if not (a.entities & b.entities or a.numbers & b.numbers or a.dates & b.dates):
                continue
            scored = score_pair(a, b)
            if scored["confidence"] < min_confidence:
                continue
            cls = classify_pair(a, b)
            pairs.append(
                {
                    "pair_class": cls,
                    "match_confidence": scored["confidence"],
                    "requires_human_confirmation": True,
                    "left": {
                        "case_id": a.case_id,
                        "venue": a.venue,
                        "title": a.title,
                        "known_outcome": a.known_outcome,
                    },
                    "right": {
                        "case_id": b.case_id,
                        "venue": b.venue,
                        "title": b.title,
                        "known_outcome": b.known_outcome,
                    },
                    "evidence": {
                        "entity_jaccard": scored["entity_jaccard"],
                        "shared_entities": scored["shared_entities"],
                        "shared_numbers": scored["shared_numbers"],
                        "shared_dates": scored["shared_dates"],
                        "settle_gap_days": scored["settle_gap_days"],
                    },
                }
            )

    class_rank = {"outcome_disagreement": 0, "resolution_asymmetry": 1, "outcome_agreement": 2}
    pairs.sort(key=lambda p: (class_rank.get(p["pair_class"], 9), -p["match_confidence"]))

    counts: dict[str, int] = {}
    for p in pairs:
        counts[p["pair_class"]] = counts.get(p["pair_class"], 0) + 1
    return {
        "pairs": pairs,
        "summary": {
            "left_venue": left_venue,
            "right_venue": right_venue,
            "left_count": len(left),
            "right_count": len(right),
            "min_confidence": min_confidence,
            "pair_count": len(pairs),
            "by_class": counts,
            "note": "Pairs are unconfirmed candidates. A curator must confirm each is the same event before it enters a holdout.",
        },
    }
