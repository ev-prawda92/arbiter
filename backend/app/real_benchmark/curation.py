from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Iterable

from .schema import validate_candidate

DOMAINS = {
    "politics": ("election", "president", "senate", "governor", "congress", "vote", "ballot"),
    "economics": ("cpi", "inflation", "gdp", "unemployment", "payroll", "fed", "interest rate"),
    "finance": ("stock", "s&p", "nasdaq", "dow", "earnings", "ipo", "treasury"),
    "sports": ("nba", "nfl", "mlb", "nhl", "soccer", "football", "basketball", "tennis", "world cup"),
    "technology": ("apple", "google", "openai", "anthropic", "ai", "semiconductor", "chip", "launch"),
    "science": ("nasa", "space", "study", "trial", "fda", "science", "research"),
    "weather": ("temperature", "rain", "snow", "hurricane", "storm", "weather"),
    "entertainment": ("oscar", "emmy", "grammy", "movie", "album", "box office", "award"),
    "geopolitics": ("war", "ceasefire", "treaty", "nato", "ukraine", "israel", "china", "taiwan"),
    "crypto": ("bitcoin", "ethereum", "crypto", "btc", "eth", "solana"),
}

BOILERPLATE_MARKERS = (
    "trademark",
    "not affiliated with",
    "for informational purposes only",
    "all rights reserved",
    "terms of use",
)

RESOLUTION_MARKERS = (
    "resolve", "resolution", "settle", "settlement", "according to", "reported by",
    "official", "if", "will be", "shall", "determined by", "source"
)

@dataclass(frozen=True)
class CurationResult:
    case_id: str
    accepted: bool
    score: int
    category: str
    rejection_reasons: list[str]
    components: dict[str, int]
    normalized_title_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _norm(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).split())


def _sha(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def classify_domain(row: dict[str, Any]) -> str:
    explicit = str(row.get("category") or "").strip().lower()
    if explicit and explicit not in {"uncategorized", "other", "unknown"}:
        return explicit
    text = _norm(f"{row.get('title', '')} {row.get('rules', '')}")
    scores = {domain: sum(1 for kw in kws if kw in text) for domain, kws in DOMAINS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "other"


def score_candidate(row: dict[str, Any]) -> CurationResult:
    title = str(row.get("title") or "").strip()
    rules = str(row.get("rules") or "").strip()
    resolution_source = str(row.get("resolution_source") or "").strip()
    evidence = row.get("benchmark_evidence") if isinstance(row.get("benchmark_evidence"), dict) else {}
    norm_rules = _norm(rules)
    norm_title = _norm(title)

    structural = 5
    schema_errors = validate_candidate(row)
    if schema_errors:
        structural = max(0, 5 - min(5, len(schema_errors)))

    definition = 0
    if len(title) >= 12:
        definition += 8
    if "?" in title or any(x in norm_title.split() for x in ("will", "does", "is", "are", "did")):
        definition += 7
    if len(rules) >= 120:
        definition += 5
    if any(token in norm_rules for token in ("greater than", "less than", "at least", "at most", "before", "after", "between")):
        definition += 5
    definition = min(25, definition)

    criteria = 0
    marker_hits = sum(1 for marker in RESOLUTION_MARKERS if marker in norm_rules)
    criteria += min(15, marker_hits * 3)
    if len(rules) >= 250:
        criteria += 5
    if resolution_source:
        criteria += 5
    criteria = min(25, criteria)

    evidence_score = 0
    if evidence:
        if evidence.get("source_url"):
            evidence_score += 8
        if evidence.get("raw_sha256"):
            evidence_score += 4
        if evidence.get("observed_value") is not None or evidence.get("observed_label") is not None:
            evidence_score += 8
    elif resolution_source.startswith("http"):
        evidence_score = 8
    evidence_score = min(20, evidence_score)

    timing = 0
    if row.get("closed_at"):
        timing += 5
    if row.get("settled_at"):
        timing += 5
    if any(token in norm_rules for token in ("utc", "et", "est", "edt", "pt", "pst", "pdt", "deadline", "before", "after", "by ")):
        timing += 5
    timing = min(15, timing)

    independence = 0
    source_url = str(evidence.get("source_url") or resolution_source or "")
    venue = str(row.get("venue") or "").lower()
    if source_url.startswith("http"):
        independence += 5
        if venue and venue not in source_url.lower():
            independence += 5
    independence = min(10, independence)

    reasons: list[str] = []
    if schema_errors:
        reasons.append("schema_invalid")
    boilerplate_hits = sum(1 for marker in BOILERPLATE_MARKERS if marker in norm_rules)
    if boilerplate_hits and marker_hits <= 1:
        reasons.append("boilerplate_or_template_rules")
    if definition < 15:
        reasons.append("definition_unclear")
    if criteria < 15:
        reasons.append("resolution_criteria_weak")
    if evidence_score < 8:
        reasons.append("evidence_path_missing")
    if timing < 5:
        reasons.append("timing_context_weak")

    components = {
        "definition_clarity": definition,
        "resolution_criteria": criteria,
        "evidence_availability": evidence_score,
        "timing_clarity": timing,
        "source_independence": independence,
        "structural_quality": structural,
    }
    score = sum(components.values())
    accepted = score >= 80 and not any(r in reasons for r in ("schema_invalid", "boilerplate_or_template_rules"))
    return CurationResult(
        case_id=str(row.get("case_id") or ""),
        accepted=accepted,
        score=score,
        category=classify_domain(row),
        rejection_reasons=reasons if not accepted else [],
        components=components,
        normalized_title_sha256=_sha(norm_title),
    )


def curate_candidates(rows: Iterable[dict[str, Any]], min_score: int = 80) -> dict[str, Any]:
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    seen_titles: set[str] = set()
    seen_raw: set[str] = set()

    for row in rows:
        result = score_candidate(row)
        reasons = list(result.rejection_reasons)
        title_key = result.normalized_title_sha256
        raw_key = str(row.get("raw_sha256") or "")
        if title_key in seen_titles or (raw_key and raw_key in seen_raw):
            reasons.append("duplicate_or_near_duplicate")
        seen_titles.add(title_key)
        if raw_key:
            seen_raw.add(raw_key)

        accepted_now = result.score >= min_score and not reasons
        enriched = dict(row)
        enriched["category"] = result.category
        enriched["curation"] = {
            **result.to_dict(),
            "accepted": accepted_now,
            "rejection_reasons": reasons,
            "minimum_score": min_score,
        }
        (accepted if accepted_now else rejected).append(enriched)

    accepted.sort(key=lambda r: (-int(r["curation"]["score"]), str(r.get("case_id") or "")))
    rejected.sort(key=lambda r: (-int(r["curation"]["score"]), str(r.get("case_id") or "")))
    category_counts: dict[str, int] = {}
    for row in accepted:
        category_counts[row["category"]] = category_counts.get(row["category"], 0) + 1
    rejection_counts: dict[str, int] = {}
    for row in rejected:
        for reason in row["curation"]["rejection_reasons"]:
            rejection_counts[reason] = rejection_counts.get(reason, 0) + 1

    return {
        "schema": "arbiter.real-benchmark-curation.v1",
        "input_count": len(accepted) + len(rejected),
        "accepted_count": len(accepted),
        "rejected_count": len(rejected),
        "minimum_score": min_score,
        "categories": dict(sorted(category_counts.items())),
        "rejection_reasons": dict(sorted(rejection_counts.items())),
        "accepted": accepted,
        "rejected": rejected,
    }


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            if not line.strip():
                continue
            obj = json.loads(line)
            if not isinstance(obj, dict):
                raise ValueError(f"line {line_no} is not a JSON object")
            rows.append(obj)
    return rows


def write_jsonl(path: str | Path, rows: Iterable[dict[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True, default=str) + "\n")
