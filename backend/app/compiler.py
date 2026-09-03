"""Arbiter Resolution Compiler v0.1.

Compiles natural-language market rules into a proposed machine-readable
ResolutionSpecification. The compiler is deterministic and conservative:
missing/ambiguous fields remain unresolved rather than being invented.
"""
from __future__ import annotations

import re
from typing import Any

from .resolution_infra import canonical_hash
from .control_library import evaluate_spec

COMPILER_VERSION = "0.1.2"

AUTHORITY_PATTERNS = [
    ("AUTH-BLS-CPI", re.compile(r"\b(?:BLS|Bureau of Labor Statistics|consumer price index|\bCPI\b)\b", re.I)),
    ("AUTH-FED-FOMC", re.compile(r"\b(?:Federal Reserve|FOMC|fed funds|federal funds)\b", re.I)),
    ("AUTH-NOAA-WEATHER", re.compile(r"\b(?:NOAA|NWS|National Weather Service|weather\.gov)\b", re.I)),
]

SUBJECTIVE = re.compile(r"\b(?:significant|major|substantial|meaningful|officially successful|credible|widely considered|generally recognized)\b", re.I)
TIMEZONE = re.compile(r"\b(?:UTC|GMT|EST|EDT|CST|CDT|MST|MDT|PST|PDT|America/[A-Za-z_]+|Europe/[A-Za-z_]+|Asia/[A-Za-z_]+)\b", re.I)
TIME_OF_DAY = re.compile(r"\b(?:[01]?\d|2[0-3]):[0-5]\d\b|\b(?:noon|midnight|open|close|closing|settlement)\b", re.I)
DATE = re.compile(r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2}(?:,\s*\d{4})?\b", re.I)
DATE_WINDOW = re.compile(r"\b(?:by\s+)?(?:the\s+)?end\s+of\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{4}\b", re.I)
NUMERIC = re.compile(r"(?:\$|€|£)?\s*(-?\d+(?:\.\d+)?)\s*(%|°?F|°?C|bps|points?|dollars?|USD)?", re.I)

TOPIC_PATTERNS = {
    "inflation": re.compile(r"\b(?:CPI|consumer price index|inflation)\b", re.I),
    "shutdown": re.compile(r"\b(?:government shutdown|shutdown|lapse in appropriations)\b", re.I),
    "weather": re.compile(r"\b(?:temperature|weather|NOAA|NWS|National Weather Service|degrees?|°[FC])\b", re.I),
    "oil": re.compile(r"\b(?:WTI|crude oil|NYMEX|oil futures?)\b", re.I),
    "rates": re.compile(r"\b(?:Federal Reserve|FOMC|fed funds|federal funds|interest rates?)\b", re.I),
    "election": re.compile(r"\b(?:election|elected|wins?|ballot|vote|certified)\b", re.I),
    "ceasefire": re.compile(r"\b(?:ceasefire|truce|hostilities)\b", re.I),
    "crypto": re.compile(r"\b(?:bitcoin|BTC|ethereum|ETH|crypto)\b", re.I),
    "recession": re.compile(r"\b(?:recession|GDP contraction|economic contraction)\b", re.I),
}

def _title_rules_consistency(title: str, rules: str) -> tuple[dict[str, Any], list[str]]:
    title_topics = {name for name, pat in TOPIC_PATTERNS.items() if pat.search(title)}
    rule_topics = {name for name, pat in TOPIC_PATTERNS.items() if pat.search(rules)}
    evidence = {"title_topics": sorted(title_topics), "rule_topics": sorted(rule_topics)}
    if title_topics and rule_topics and title_topics.isdisjoint(rule_topics):
        return evidence, ["contract.title_rules_mismatch"]
    return evidence, []


def _span(text: str, match: re.Match | None) -> dict[str, Any] | None:
    if not match:
        return None
    return {"text": match.group(0), "start": match.start(), "end": match.end()}


def _definition(title: str, rules: str) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    text = f"{title}\n{rules}"
    unresolved: list[str] = []
    provenance: dict[str, Any] = {}
    lower = text.lower()
    op = None
    for token, normalized in [
        (r"\bat least\b|>=|\breach(?:es|ed)?\b|\bexceed(?:s|ed)?\b", ">="),
        (r"\babove\b|\bmore than\b|>", ">"),
        (r"\bat most\b|<=", "<="),
        (r"\bbelow\b|\bunder\b|\bless than\b|<", "<"),
        (r"\bequal(?:s| to)?\b|==", "=="),
    ]:
        m = re.search(token, text, re.I)
        if m:
            op = normalized
            provenance["operator"] = _span(text, m)
            break
    threshold = None
    threshold_unit = ""
    m = None
    # A threshold should be semantically adjacent to its comparison operator;
    # do not mistake dates or clock values for the settlement threshold.
    if op and "operator" in provenance:
        start = provenance["operator"]["end"]
        local = NUMERIC.search(text, start, min(len(text), start + 48))
        if local:
            m = local
    if m is None:
        nums = list(NUMERIC.finditer(title))
        # Exclude obvious four-digit years when falling back to title numbers.
        candidates = [x for x in nums if not (x.group(1).isdigit() and len(x.group(1)) == 4 and 1900 <= int(x.group(1)) <= 2100)]
        m = candidates[0] if candidates else None
    if m:
        try:
            threshold = float(m.group(1))
            threshold_unit = (m.group(2) or "").strip()
            provenance["threshold"] = _span(text, m)
        except ValueError:
            pass

    subjective = SUBJECTIVE.search(text)
    if subjective:
        unresolved.append("definition.subjective_term")
        provenance["subjective_term"] = _span(text, subjective)

    if op and threshold is not None:
        definition = {"type": "numeric_threshold", "operator": op, "threshold": threshold}
        if threshold_unit:
            definition["unit"] = threshold_unit
    else:
        rate_cut = re.search(r"\b(?:interest\s+rate\s+cut|cut(?:s|ting|ted)?\s+(?:the\s+)?(?:federal\s+funds|fed\s+funds|interest)\s+rate)\b", text, re.I)
        declaration = re.search(r"\b(?:declare(?:s|d)?|certif(?:y|ies|ied)|announc(?:e|es|ed|ement)|publish(?:es|ed)?|report(?:s|ed)?|wins?|elected|shutdown|ceasefire)\b", text, re.I)
        if rate_cut and not subjective:
            definition = {"type": "rate_change_event", "direction": "cut", "criterion": rules.strip() or title.strip()}
            provenance["criterion"] = _span(text, rate_cut)
        elif declaration and not subjective:
            definition = {"type": "official_fact", "criterion": rules.strip() or title.strip()}
            provenance["criterion"] = _span(text, declaration)
        else:
            definition = {}
            unresolved.append("definition.objective_condition")
    return definition, provenance, unresolved


def _timing(title: str, rules: str) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    text = f"{title}\n{rules}"
    provenance: dict[str, Any] = {}
    unresolved: list[str] = []
    dm = DATE.search(text)
    wm = DATE_WINDOW.search(text)
    tm = TIME_OF_DAY.search(text)
    zm = TIMEZONE.search(text)
    timing: dict[str, Any] = {}
    if dm:
        timing["observation_date_text"] = dm.group(0)
        provenance["date"] = _span(text, dm)
    elif wm:
        timing["observation_window_text"] = wm.group(0)
        timing["window_kind"] = "end_of_period"
        provenance["date_window"] = _span(text, wm)
    else:
        unresolved.append("timing.date")
    if tm:
        timing["observation_time_text"] = tm.group(0)
        provenance["time"] = _span(text, tm)
    else:
        unresolved.append("timing.time_of_day")
    if zm:
        timing["timezone"] = zm.group(0)
        provenance["timezone"] = _span(text, zm)
    else:
        unresolved.append("timing.timezone")
    return timing, provenance, unresolved


def _authorities(title: str, rules: str, known_authorities: list[dict[str, Any]]) -> tuple[list[str], list[str], dict[str, Any], list[str]]:
    text = f"{title}\n{rules}"
    found: list[str] = []
    provenance: dict[str, Any] = {}
    by_id = {a.get("authority_id"): a for a in known_authorities}
    for aid, pat in AUTHORITY_PATTERNS:
        m = pat.search(text)
        if m and aid in by_id:
            found.append(aid)
            provenance[aid] = _span(text, m)

    # Also match registered authority names/organizations exactly enough for local custom authorities.
    for a in known_authorities:
        aid = a.get("authority_id")
        if not aid or aid in found:
            continue
        for key in ("name", "organization"):
            val = str(a.get(key) or "").strip()
            if len(val) >= 4:
                m = re.search(re.escape(val), text, re.I)
                if m:
                    found.append(aid)
                    provenance[aid] = _span(text, m)
                    break

    unresolved = [] if found else ["source.authority"]
    precedence: list[str] = []
    if len(found) == 1:
        precedence = found.copy()
    elif len(found) > 1:
        # Do not invent precedence. Explicit ordering language is required.
        if re.search(r"\b(?:primary|secondary|fallback|if unavailable|takes precedence|in order)\b", text, re.I):
            precedence = found.copy()
        else:
            unresolved.append("source.precedence")
    return found, precedence, provenance, unresolved


def _revision_policy(rules: str) -> tuple[dict[str, Any], list[str]]:
    if not re.search(r"\b(?:revis(?:e|ed|ion)|preliminary|final release|first release|initial release)\b", rules, re.I):
        return {}, []
    if re.search(r"\b(?:first|initial) release\b", rules, re.I):
        return {"policy": "first_release"}, []
    if re.search(r"\bfinal(?:ized)?(?: release| value| report)?\b", rules, re.I):
        return {"policy": "final_release"}, []
    return {}, ["revision.policy"]


def _recommended_fixes(unresolved: list[str]) -> list[dict[str, str]]:
    mapping = {
        "timing.date": ("Timing", "Specify the governing observation date or settlement window."),
        "timing.time_of_day": ("Timing", "Specify the exact cutoff or observation time."),
        "timing.timezone": ("Timing", "Specify the timezone for the governing cutoff."),
        "definition.objective_condition": ("Definition", "State the exact objective event or value that produces YES versus NO."),
        "definition.subjective_term": ("Definition", "Replace subjective language with an objectively verifiable condition."),
        "source.authority": ("Source", "Name an approved resolution authority or source."),
        "source.precedence": ("Source", "Define which source controls and the fallback order if multiple sources are allowed."),
        "revision.policy": ("Source", "Specify whether the first release, final release, or another revision cutoff controls."),
        "contract.title_rules_mismatch": ("Contract", "Align the market title with the governing resolution criteria before listing."),
    }
    out = []
    for field in unresolved:
        lever, action = mapping.get(field, ("Specification", f"Resolve {field} before automated resolution."))
        out.append({"field": field, "lever": lever, "action": action})
    return out


def compile_rules(contract_id: str, title: str, rules: str, known_authorities: list[dict[str, Any]], contract_version: int = 1, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    consistency, unresolved_consistency = _title_rules_consistency(title, rules)
    # If title and rules conflict, rule text becomes the only trusted source for
    # compilation. This prevents a title-only CPI token, for example, from
    # producing a trusted BLS authority when the governing rules describe an
    # unrelated shutdown contract.
    extraction_title = "" if unresolved_consistency else title
    definition, def_prov, unresolved_def = _definition(extraction_title, rules)
    timing, time_prov, unresolved_time = _timing(extraction_title, rules)
    authority_ids, precedence, auth_prov, unresolved_auth = _authorities(extraction_title, rules, known_authorities)
    revision_policy, unresolved_revision = _revision_policy(rules)

    unresolved = list(dict.fromkeys(unresolved_auth + unresolved_time + unresolved_def + unresolved_revision + unresolved_consistency))
    spec = {
        "contract_id": contract_id,
        "contract_version": contract_version,
        "title": title.strip(),
        "definition": definition,
        "timing": timing,
        "authority_ids": authority_ids,
        "source_precedence": precedence,
        "revision_policy": revision_policy,
        "fallback_policy": {},
        "approval_policy": {"auto_if_all_controls_pass": True},
        "metadata": {**(metadata or {}), "compiled_from_rules": True, "compiler_version": COMPILER_VERSION},
        "schema": "arbiter.resolution-spec.v1",
    }
    known = {a.get("authority_id") for a in known_authorities}
    controls = evaluate_spec(spec, known)
    block = any(c["status"] == "BLOCK" for c in controls) or "contract.title_rules_mismatch" in unresolved
    review = any(c["status"] == "REVIEW" for c in controls) or bool(unresolved)
    status = "BLOCK" if block else ("REVIEW" if review else "READY")

    result = {
        "compiler_version": COMPILER_VERSION,
        "status": status,
        "proposed_spec": spec,
        "unresolved_fields": unresolved,
        "provenance": {"source": auth_prov, "timing": time_prov, "definition": def_prov, "consistency": consistency},
        "field_trust": {
            "title": "CONFLICTED" if unresolved_consistency else "TRUSTED",
            "rules": "TRUSTED",
            "compiled_from": "rules_only" if unresolved_consistency else "title_and_rules",
        },
        "controls": controls,
        "recommended_fixes": _recommended_fixes(unresolved),
        "status_reason": (
            "Specification is complete enough to proceed to evidence monitoring." if status == "READY" else
            "Specification is coherent but requires governed repair or approval before automated resolution." if status == "REVIEW" else
            "Specification has a blocking inconsistency or missing binding field and cannot proceed."
        ),
        "boundary": "Compiler output is a proposal. Unresolved fields are never fabricated; binding resolution remains governed and deterministic.",
    }
    result["compilation_hash"] = canonical_hash(result)
    return result
