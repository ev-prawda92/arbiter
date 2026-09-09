from __future__ import annotations

from collections import Counter
from typing import Any


def _rate(n: int, d: int) -> float | None:
    return round(n / d, 4) if d else None


def summarize(predictions: list[dict[str, Any]], labels: list[dict[str, Any]]) -> dict[str, Any]:
    by_id = {str(x.get("case_id")): x for x in labels}
    paired = [(p, by_id.get(str(p.get("case_id")))) for p in predictions]
    paired = [(p, l) for p, l in paired if l is not None]

    compiler_counts = Counter(str(p.get("compiler_status") or "UNKNOWN") for p, _ in paired)
    semantic_counts = Counter(str(p.get("semantic_status") or "UNKNOWN") for p, _ in paired)
    verdict_counts = Counter(str(p.get("engine_verdict") or "UNKNOWN") for p, _ in paired)
    prediction_counts = Counter(str(p.get("predicted_outcome") or "UNKNOWN") for p, _ in paired)
    actual_outcomes = Counter(str(l.get("known_outcome") or "UNKNOWN") for _, l in paired)
    venues = Counter(str(p.get("venue") or "unknown") for p, _ in paired)
    categories = Counter(str(p.get("category") or "uncategorized") for p, _ in paired)

    unresolved = Counter()
    for p, _ in paired:
        unresolved.update(str(x) for x in (p.get("unresolved_fields") or []))

    known_outcome_rows = [(p, l) for p, l in paired if l.get("known_outcome") in {"YES", "NO"}]
    outcome_scored = [(p, l) for p, l in known_outcome_rows if p.get("predicted_outcome") in {"YES", "NO"}]
    outcome_correct = sum(1 for p, l in outcome_scored if p.get("predicted_outcome") == l.get("known_outcome"))
    held_rows = [(p, l) for p, l in known_outcome_rows if p.get("predicted_outcome") == "HOLD"]
    evidence_rows = [(p, l) for p, l in known_outcome_rows if p.get("evidence_present") is True]
    evidence_resolved_rows = [(p, l) for p, l in evidence_rows if p.get("predicted_outcome") in {"YES", "NO"}]

    gold_status_rows = [(p, l) for p, l in paired if l.get("gold_status") in {"READY", "REVIEW", "BLOCK"}]
    gold_status_correct = sum(1 for p, l in gold_status_rows if p.get("compiler_status") == l.get("gold_status"))
    ready_rows = [(p, l) for p, l in gold_status_rows if l.get("gold_status") == "READY"]
    false_holds = sum(1 for p, _ in ready_rows if p.get("compiler_status") != "READY")

    gold_unresolved_rows = [(p, l) for p, l in paired if isinstance(l.get("gold_unresolved_fields"), list)]
    planted_total = 0
    planted_detected = 0
    extra_flags = 0
    for p, l in gold_unresolved_rows:
        gold = {str(x) for x in (l.get("gold_unresolved_fields") or [])}
        pred = {str(x) for x in (p.get("unresolved_fields") or [])}
        planted_total += len(gold)
        planted_detected += len(gold & pred)
        extra_flags += len(pred - gold)

    dimension_metrics: dict[str, Any] = {}
    for dim in ("source", "timing", "definition"):
        rows = [(p, l) for p, l in paired if l.get(f"gold_{dim}") is not None]
        exact = 0
        for p, l in rows:
            gold = l.get(f"gold_{dim}")
            score = p.get(f"{dim}_score")
            if isinstance(gold, bool):
                predicted_pass = isinstance(score, (int, float)) and score <= 20
                exact += int(predicted_pass == gold)
            elif isinstance(gold, (int, float)) and isinstance(score, (int, float)):
                exact += int(abs(float(score) - float(gold)) <= 10.0)
        dimension_metrics[f"{dim}_gold_coverage"] = len(rows)
        dimension_metrics[f"{dim}_agreement"] = _rate(exact, len(rows))

    return {
        "case_count": len(paired),
        "venues": dict(venues),
        "categories": dict(categories),
        "actual_outcomes": dict(actual_outcomes),
        "compiler_statuses": dict(compiler_counts),
        "semantic_statuses": dict(semantic_counts),
        "engine_verdicts": dict(verdict_counts),
        "prediction_outcomes": dict(prediction_counts),
        "top_unresolved_fields": unresolved.most_common(15),
        "outcome_metrics": {
            "known_outcome_cases": len(known_outcome_rows),
            "evidence_cases": len(evidence_rows),
            "evidence_coverage": _rate(len(evidence_rows), len(known_outcome_rows)),
            "scored_cases": len(outcome_scored),
            "resolution_coverage": _rate(len(outcome_scored), len(known_outcome_rows)),
            "evidence_resolution_rate": _rate(len(evidence_resolved_rows), len(evidence_rows)),
            "agreement": _rate(outcome_correct, len(outcome_scored)),
            "held_cases": len(held_rows),
            "hold_rate": _rate(len(held_rows), len(known_outcome_rows)),
            "note": "Outcome agreement is conditional on a blind evidence-backed YES/NO resolution. HOLD is a governed abstention, not silently counted as an incorrect directional guess.",
        },
        "gold_contract_quality": {
            "gold_status_coverage": len(gold_status_rows),
            "gold_status_accuracy": _rate(gold_status_correct, len(gold_status_rows)),
            "gold_ready_cases": len(ready_rows),
            "false_hold_rate_on_gold_ready": _rate(false_holds, len(ready_rows)),
            "gold_unresolved_case_coverage": len(gold_unresolved_rows),
            "ambiguity_recall": _rate(planted_detected, planted_total),
            "extra_unresolved_flags": extra_flags if gold_unresolved_rows else None,
            **dimension_metrics,
            "note": "These accuracy metrics remain null until independent/human gold contract-quality labels are frozen before the blind run.",
        },
    }
