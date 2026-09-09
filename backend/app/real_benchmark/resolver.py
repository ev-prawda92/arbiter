from __future__ import annotations

import math
from typing import Any


_TRUE_LABELS = {"yes", "y", "true", "1", "occurred", "happened", "met", "pass", "passed"}
_FALSE_LABELS = {"no", "n", "false", "0", "did not occur", "not occurred", "not met", "fail", "failed"}


def _as_number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        x = float(value)
        return x if math.isfinite(x) else None
    text = str(value).strip().replace(",", "")
    # Permit common evidence values such as "$12.4" and "3.1%" while keeping
    # the comparison unit governed by the compiled contract specification.
    for token in ("$", "€", "£"):
        text = text.replace(token, "")
    if text.endswith("%"):
        text = text[:-1].strip()
    try:
        x = float(text)
    except ValueError:
        return None
    return x if math.isfinite(x) else None


def _as_binary_label(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    text = " ".join(str(value or "").strip().lower().split())
    if text in _TRUE_LABELS:
        return True
    if text in _FALSE_LABELS:
        return False
    return None


def resolve_from_compiled_spec(compilation: dict[str, Any], evidence: dict[str, Any] | None) -> dict[str, Any]:
    """Deterministically resolve a compiled contract against a frozen evidence row.

    This function is deliberately narrow. It never reads venue outcome labels and
    never asks a model to decide settlement. If the compiler gate is not READY,
    evidence is missing, or the definition type is unsupported/ambiguous, the
    result is HOLD rather than a guessed YES/NO.
    """
    status = str(compilation.get("status") or "UNKNOWN").upper()
    if status != "READY":
        return {
            "predicted_outcome": "HOLD",
            "reason": f"Compiler status is {status}; governed benchmark resolution does not bypass READY gating.",
            "resolution_method": "governed-hold",
        }
    if not evidence:
        return {
            "predicted_outcome": "HOLD",
            "reason": "No independently frozen evidence row is available for this case.",
            "resolution_method": "evidence-missing",
        }

    spec = compilation.get("proposed_spec") or {}
    definition = spec.get("definition") or {}
    kind = str(definition.get("type") or "")

    if kind == "numeric_threshold":
        observed = _as_number(evidence.get("observed_value"))
        threshold = _as_number(definition.get("threshold"))
        operator = str(definition.get("operator") or "")
        if observed is None or threshold is None or operator not in {">", ">=", "<", "<=", "=="}:
            return {
                "predicted_outcome": "HOLD",
                "reason": "Numeric threshold could not be evaluated deterministically from the frozen evidence.",
                "resolution_method": "numeric-threshold-hold",
            }
        result = {
            ">": observed > threshold,
            ">=": observed >= threshold,
            "<": observed < threshold,
            "<=": observed <= threshold,
            "==": observed == threshold,
        }[operator]
        return {
            "predicted_outcome": "YES" if result else "NO",
            "reason": f"Frozen observed value {observed:g} evaluated {operator} compiled threshold {threshold:g}.",
            "resolution_method": "numeric-threshold-v1",
            "observed_value_normalized": observed,
            "threshold_normalized": threshold,
            "operator": operator,
        }

    if kind in {"official_fact", "rate_change_event"}:
        observed = _as_binary_label(evidence.get("observed_label"))
        if observed is None:
            observed = _as_binary_label(evidence.get("observed_value"))
        if observed is None:
            return {
                "predicted_outcome": "HOLD",
                "reason": f"{kind} requires a frozen boolean/YES-NO evidence observation.",
                "resolution_method": f"{kind}-hold",
            }
        return {
            "predicted_outcome": "YES" if observed else "NO",
            "reason": f"Frozen evidence states the compiled {kind.replace('_', ' ')} criterion {'occurred' if observed else 'did not occur'}.",
            "resolution_method": f"{kind}-v1",
        }

    return {
        "predicted_outcome": "HOLD",
        "reason": f"Compiled definition type {kind or 'missing'} is not supported by the v0.27 deterministic evidence resolver.",
        "resolution_method": "unsupported-definition-hold",
    }
