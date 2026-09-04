"""Arbiter Semantic Contract Intelligence v0.13.

This layer explains what a natural-language event contract is actually asking,
identifies domain concepts, extracts the semantic dimensions required for a
binding resolution, and surfaces ambiguity without inventing missing meaning.

It is intentionally advisory in v0.13. The deterministic compiler/resolution
engine remains the binding gate while semantic findings are introduced and
benchmarked. A later governed policy can promote selected semantic findings to
binding pre-listing controls.
"""
from __future__ import annotations

import re
from typing import Any

from .resolution_infra import canonical_hash

SEMANTIC_VERSION = "0.13.0"

_MONTH = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"


def _found(pattern: str, text: str) -> str | None:
    m = re.search(pattern, text, re.I)
    return m.group(0) if m else None


def _clarification(field: str, question: str, why: str, severity: str = "REVIEW") -> dict[str, str]:
    return {"field": field, "question": question, "why": why, "severity": severity}


def _cpi_semantics(text: str) -> dict[str, Any]:
    extracted: dict[str, Any] = {}
    clarifications: list[dict[str, str]] = []

    if re.search(r"\bCPI[- ]?U\b|Consumer Price Index for All Urban Consumers", text, re.I):
        extracted["series"] = "CPI-U"
    elif re.search(r"\bCPI[- ]?W\b|Urban Wage Earners", text, re.I):
        extracted["series"] = "CPI-W"
    elif re.search(r"\bcore\s+CPI\b|CPI.*less food and energy", text, re.I):
        extracted["series"] = "CPI-U Less Food and Energy"
    else:
        clarifications.append(_clarification(
            "semantic.metric_series",
            "Which CPI series governs the market (for example CPI-U All Items, CPI-W, or Core CPI)?",
            "'CPI' names a family of indexes rather than one unique data series.",
        ))

    if re.search(r"year[- ]over[- ]year|\by/?y\b|12[- ]month|from (?:a|one) year (?:earlier|ago)", text, re.I):
        extracted["measurement_basis"] = "year_over_year_percent_change"
    elif re.search(r"month[- ]over[- ]month|\bm/?m\b|from (?:the )?previous month", text, re.I):
        extracted["measurement_basis"] = "month_over_month_percent_change"
    elif re.search(r"index (?:level|value)|CPI (?:level|index)", text, re.I):
        extracted["measurement_basis"] = "index_level"
    else:
        clarifications.append(_clarification(
            "semantic.measurement_basis",
            "Does the threshold apply to year-over-year CPI, month-over-month CPI, or the index level?",
            "A percentage threshold such as 3.0% is ambiguous without the measurement basis.",
        ))

    if re.search(r"not seasonally adjusted|unadjusted|\bNSA\b", text, re.I):
        extracted["seasonal_adjustment"] = "not_seasonally_adjusted"
    elif re.search(r"seasonally adjusted|seasonal(?:ly)? adjusted|\bSA\b", text, re.I):
        extracted["seasonal_adjustment"] = "seasonally_adjusted"
    else:
        clarifications.append(_clarification(
            "semantic.seasonal_adjustment",
            "Should the governing CPI observation be seasonally adjusted or not seasonally adjusted?",
            "BLS publishes measures on different adjustment bases and the contract should pin the intended one.",
            severity="INFO",
        ))

    if re.search(r"\bU\.S\.|\bUS\b|United States|national", text, re.I):
        extracted["geography"] = "United States"
    else:
        clarifications.append(_clarification(
            "semantic.geography",
            "What geography does the CPI observation cover?",
            "The governing population/geography should be explicit for reproducible resolution.",
        ))

    # Reference period and publication date are distinct concepts. Detect explicit
    # reference-month language separately from a dated release/observation.
    ref = _found(rf"(?:for|reference month(?: of)?|covering)\s+{_MONTH}\s+\d{{4}}", text)
    if ref:
        extracted["reference_period_text"] = ref
    else:
        clarifications.append(_clarification(
            "semantic.reference_period",
            "Which CPI reference month/period is being measured?",
            "The month in which BLS publishes CPI is not necessarily the month the CPI observation describes.",
        ))

    if re.search(r"Bureau of Labor Statistics|\bBLS\b", text, re.I):
        extracted["publisher"] = "U.S. Bureau of Labor Statistics"
    else:
        clarifications.append(_clarification(
            "semantic.publisher",
            "Which authoritative publisher controls the CPI result?",
            "The semantic metric must map to an explicit authoritative publication.",
        ))

    if re.search(r"first (?:published )?release|initial release|first print", text, re.I):
        extracted["revision_semantics"] = "first_release"
    elif re.search(r"final release|final value|latest revised|revised value", text, re.I):
        extracted["revision_semantics"] = "final_or_revised"
    else:
        clarifications.append(_clarification(
            "semantic.revision_semantics",
            "Does the first published CPI value control, or can later revisions change the result?",
            "Revision semantics determine which real-world observation is legally/operationally binding.",
        ))

    return {
        "concept": {
            "concept_id": "MACRO.CPI",
            "name": "Consumer Price Index",
            "plain_language": "A price index published by the U.S. Bureau of Labor Statistics that tracks changes in prices paid by consumers for a basket of goods and services.",
            "domain": "macroeconomics",
        },
        "extracted": extracted,
        "clarifications": clarifications,
    }


def _fed_semantics(text: str) -> dict[str, Any]:
    extracted: dict[str, Any] = {}
    clarifications: list[dict[str, str]] = []
    if re.search(r"federal funds target range|target range", text, re.I):
        extracted["rate_instrument"] = "federal_funds_target_range"
    elif re.search(r"federal funds rate|fed funds rate", text, re.I):
        extracted["rate_instrument"] = "federal_funds_rate"
    else:
        clarifications.append(_clarification(
            "semantic.rate_instrument",
            "Which Federal Reserve rate or policy instrument must change?",
            "'Interest rates' can refer to many rates; resolution should pin the specific FOMC-controlled instrument.",
        ))
    if re.search(r"FOMC statement|Federal Open Market Committee statement", text, re.I):
        extracted["governing_publication"] = "FOMC statement"
    elif re.search(r"Federal Reserve|FOMC", text, re.I):
        clarifications.append(_clarification(
            "semantic.governing_publication",
            "Which official Federal Reserve publication is binding evidence (for example the FOMC statement)?",
            "Naming the institution alone may leave multiple official publications available.",
            severity="INFO",
        ))
    return {
        "concept": {
            "concept_id": "MONETARY_POLICY.FOMC_RATE_ACTION",
            "name": "Federal Reserve policy-rate action",
            "plain_language": "A change in the monetary-policy rate or target range set by the Federal Open Market Committee.",
            "domain": "monetary_policy",
        },
        "extracted": extracted,
        "clarifications": clarifications,
    }


def _weather_semantics(text: str) -> dict[str, Any]:
    extracted: dict[str, Any] = {}
    clarifications: list[dict[str, str]] = []
    if re.search(r"NOAA|National Weather Service|\bNWS\b", text, re.I):
        extracted["publisher"] = "NOAA/National Weather Service"
    else:
        clarifications.append(_clarification("semantic.weather_authority", "Which weather station/source controls?", "Weather observations vary by station and provider."))
    station = _found(r"(?:station|airport)\s+[A-Z0-9-]{3,8}", text)
    if station:
        extracted["station_text"] = station
    else:
        clarifications.append(_clarification("semantic.observation_location", "Which exact station or observation location controls?", "City-level weather can differ across observing stations."))
    if re.search(r"maximum|daily high|high temperature", text, re.I):
        extracted["measurement"] = "daily_max_temperature"
    elif re.search(r"minimum|daily low|low temperature", text, re.I):
        extracted["measurement"] = "daily_min_temperature"
    elif re.search(r"temperature", text, re.I):
        clarifications.append(_clarification("semantic.weather_measurement", "Is the governing value an instantaneous observation, daily high, daily low, or another statistic?", "'Temperature' alone does not identify one reproducible observation."))
    return {
        "concept": {
            "concept_id": "WEATHER.OBSERVATION",
            "name": "Weather observation",
            "plain_language": "An observed weather measurement tied to a specific location, station, time, and published source.",
            "domain": "weather",
        },
        "extracted": extracted,
        "clarifications": clarifications,
    }


def analyze_contract(title: str, rules: str) -> dict[str, Any]:
    text = f"{title}\n{rules}".strip()
    analyses: list[dict[str, Any]] = []
    if re.search(r"\bCPI\b|consumer price index|inflation", text, re.I):
        analyses.append(_cpi_semantics(text))
    if re.search(r"Federal Reserve|\bFOMC\b|fed funds|federal funds|interest rate cut", text, re.I):
        analyses.append(_fed_semantics(text))
    if re.search(r"temperature|weather|NOAA|National Weather Service|\bNWS\b", text, re.I):
        analyses.append(_weather_semantics(text))

    concepts = [a["concept"] for a in analyses]
    extracted: dict[str, Any] = {}
    clarifications: list[dict[str, str]] = []
    for a in analyses:
        extracted.update(a["extracted"])
        clarifications.extend(a["clarifications"])

    review_fields = [c["field"] for c in clarifications if c.get("severity") == "REVIEW"]
    info_fields = [c["field"] for c in clarifications if c.get("severity") == "INFO"]
    if not concepts:
        status = "UNCLASSIFIED"
        explanation = "No specialized semantic ontology matched this contract. The deterministic compiler can still inspect source, timing, and definition controls."
    elif review_fields:
        status = "REVIEW"
        explanation = "The contract contains a recognized real-world concept but leaves semantic dimensions unresolved that could change the meaning of the settlement condition."
    else:
        status = "READY"
        explanation = "The recognized semantic concept is specified across the required meaning dimensions currently covered by Arbiter's ontology."

    result = {
        "semantic_version": SEMANTIC_VERSION,
        "status": status,
        "concepts": concepts,
        "extracted_semantics": extracted,
        "unresolved_semantic_fields": review_fields,
        "informational_fields": info_fields,
        "clarification_questions": clarifications,
        "explanation": explanation,
        "boundary": "Semantic Contract Intelligence interprets and explains contract meaning. It does not itself determine settlement or fabricate missing terms.",
    }
    result["semantic_hash"] = canonical_hash(result)
    return result
