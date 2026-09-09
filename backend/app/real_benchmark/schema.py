from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Any


ALLOWED_BINARY_OUTCOMES = {"YES", "NO"}
LEAKAGE_KEYS = {
    "known_outcome", "result", "settlement_value", "settlement_value_dollars",
    "outcomePrices", "outcome_prices", "winning_outcome", "market_result",
    "label", "gold_status", "gold_unresolved_fields", "gold_source",
    "gold_timing", "gold_definition",
}


@dataclass(frozen=True)
class Candidate:
    case_id: str
    venue: str
    external_market_id: str
    title: str
    rules: str
    known_outcome: str
    source_url: str
    collected_at: str
    raw_sha256: str
    event_id: str | None = None
    resolution_source: str | None = None
    category: str | None = None
    opened_at: str | None = None
    closed_at: str | None = None
    settled_at: str | None = None
    settlement_value: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_candidate(row: dict[str, Any], min_rules_chars: int = 40) -> list[str]:
    errors: list[str] = []
    required = ["case_id", "venue", "external_market_id", "title", "rules", "known_outcome", "source_url", "collected_at", "raw_sha256"]
    for key in required:
        if row.get(key) in (None, ""):
            errors.append(f"missing {key}")
    outcome = str(row.get("known_outcome") or "").upper()
    if outcome not in ALLOWED_BINARY_OUTCOMES:
        errors.append("known_outcome must be YES or NO for v0.1 holdout")
    if len(str(row.get("rules") or "").strip()) < min_rules_chars:
        errors.append(f"rules shorter than {min_rules_chars} characters")
    if not str(row.get("raw_sha256") or "").startswith("sha256:"):
        errors.append("raw_sha256 must be sha256:<hex>")
    if not str(row.get("source_url") or "").startswith("http"):
        errors.append("source_url must be an http(s) URL")
    return errors


def contract_input_from_candidate(row: dict[str, Any]) -> dict[str, Any]:
    """Return the blind benchmark input. No result/label fields are copied."""
    metadata = dict(row.get("metadata") or {})
    # Be defensive if a venue payload was accidentally stuffed into metadata.
    for key in list(metadata):
        if key in LEAKAGE_KEYS or "outcome" in key.lower() or "settlement_value" in key.lower():
            metadata.pop(key, None)
    return {
        "case_id": str(row["case_id"]),
        "venue": str(row["venue"]),
        "external_market_id": str(row["external_market_id"]),
        "event_id": row.get("event_id"),
        "title": str(row["title"]),
        "rules": str(row["rules"]),
        "resolution_source": row.get("resolution_source"),
        "category": row.get("category") or "uncategorized",
        "opened_at": row.get("opened_at"),
        "closed_at": row.get("closed_at"),
        "metadata": metadata,
    }


def label_from_candidate(row: dict[str, Any], frozen_at: str) -> dict[str, Any]:
    label = {
        "case_id": str(row["case_id"]),
        "known_outcome": str(row["known_outcome"]).upper(),
        "settlement_value": row.get("settlement_value"),
        "label_frozen_at": frozen_at,
        "label_source": row.get("source_url"),
    }
    # Optional independently/human supplied contract-quality gold fields.
    for key in (
        "gold_status", "gold_unresolved_fields", "gold_source", "gold_timing",
        "gold_definition", "gold_notes", "gold_reviewed_by", "gold_reviewed_at",
    ):
        if key in row:
            label[key] = row.get(key)
    return label


def provenance_from_candidate(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "case_id": str(row["case_id"]),
        "venue": str(row["venue"]),
        "external_market_id": str(row["external_market_id"]),
        "source_url": str(row["source_url"]),
        "collected_at": str(row["collected_at"]),
        "raw_sha256": str(row["raw_sha256"]),
        "settled_at": row.get("settled_at"),
    }




def evidence_from_candidate(row: dict[str, Any]) -> dict[str, Any] | None:
    """Return independently curated evidence that is safe for the blind runner.

    Evidence may imply an outcome when evaluated against the contract—that is the
    point of an evidence-backed resolution benchmark—but it must never contain the
    venue outcome/gold label itself.
    """
    raw = row.get("benchmark_evidence")
    if not isinstance(raw, dict) or not raw:
        return None
    leakage = detect_label_leakage(raw)
    if leakage:
        raise ValueError(f"benchmark_evidence contains forbidden label fields: {', '.join(leakage[:6])}")
    if raw.get("observed_value") is None and raw.get("observed_label") is None:
        raise ValueError("benchmark_evidence requires observed_value or observed_label")
    source_url = str(raw.get("source_url") or "").strip()
    if not source_url.startswith("http"):
        raise ValueError("benchmark_evidence requires source_url")
    raw_hash = str(raw.get("raw_sha256") or "").strip()
    if not raw_hash.startswith("sha256:"):
        raise ValueError("benchmark_evidence requires raw_sha256")
    return {
        "case_id": str(row["case_id"]),
        "observed_value": raw.get("observed_value"),
        "observed_label": raw.get("observed_label"),
        "unit": raw.get("unit"),
        "authority": raw.get("authority"),
        "source_url": source_url,
        "retrieved_at": raw.get("retrieved_at"),
        "raw_sha256": raw_hash,
    }

def detect_label_leakage(value: Any, path: str = "$") -> list[str]:
    hits: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            low = str(key).lower()
            if key in LEAKAGE_KEYS or low in {k.lower() for k in LEAKAGE_KEYS} or "winning_outcome" in low:
                hits.append(f"{path}.{key}")
            hits.extend(detect_label_leakage(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for i, child in enumerate(value):
            hits.extend(detect_label_leakage(child, f"{path}[{i}]"))
    return hits
