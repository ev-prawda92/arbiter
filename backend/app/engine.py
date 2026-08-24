"""
Arbiter resolution-integrity engine.

Design principle: the scoring logic is deterministic and inspectable. The entire
value of an *independent* resolution layer is that the logic does not live inside
the exchange's own walls and can be audited line by line. So every score here is
produced by explicit rules, never by an opaque model. (An optional LLM pass is
available separately in llm.py for triage, but it never overrides these rules.)

A contract is scored on the three levers that decide who gets paid:
  - source      : is there one authoritative, timely settlement source?
  - timing      : is the settlement clock exact (date + time + zone + revisions)?
  - definition  : does the question map to a cleanly verifiable fact?

Each lever is 0-100 where HIGHER = MORE dispute risk. Composite is a weighted sum.
Thresholds turn the composite into a verdict. Weights and thresholds come from the
policy module so the exchange's team can govern them (versioned, logged) without
touching this code.
"""

import hashlib
import re
from datetime import datetime, timezone

# ------------------------------------------------------------------ source lever

# Authoritative, named settlement sources. Presence of one lowers source risk.
AUTHORITATIVE_SOURCES = [
    r"\bNWS\b", r"national weather service", r"\bNOAA\b",
    r"\bBLS\b", r"bureau of labor statistics",
    r"\bOPM\b", r"office of personnel management",
    r"\bCME\b", r"\bNYMEX\b", r"\bCOMEX\b", r"\bLME\b",
    r"federal reserve", r"\bFOMC\b", r"\bFed\b",
    r"\bBEA\b", r"bureau of economic analysis",
    r"\bNBER\b", r"\bCFTC\b", r"\bSEC\b", r"\bTreasury\b",
    r"associated press", r"\bAP\b race call", r"official (results|settlement|report|statement|data|source)",
]

# Vague / non-authoritative source language raises source risk sharply.
VAGUE_SOURCES = [
    r"credible (news|reporting|media|sources?)", r"media reports?",
    r"news reports?", r"widely reported", r"reputable sources?",
    r"generally recognized", r"consensus of", r"reasonable interpretation",
]

REVISION_PRONE = [r"\bCPI\b", r"\bGDP\b", r"payrolls?", r"jobs report", r"revised", r"revision"]


def score_source(text, title):
    blob = f"{title}\n{text}".lower()
    raw = f"{title}\n{text}"
    flags = []
    score = 18  # neutral-ish baseline: assume some risk until a clean source is proven

    has_auth = any(re.search(p, raw, re.I) for p in AUTHORITATIVE_SOURCES)
    has_vague = any(re.search(p, blob, re.I) for p in VAGUE_SOURCES)
    named_source = bool(re.search(r"source\s*[:\-]", blob)) or has_auth

    if has_auth:
        score -= 12
    else:
        score += 8
        flags.append("no clearly authoritative source named")

    if has_vague:
        score += 55
        flags.append("relies on vague / non-authoritative reporting")

    if not named_source and not has_vague:
        score += 22
        flags.append("settlement source not explicitly designated")

    # multiple sources with no stated hierarchy (e.g. "COMEX or LME", "A and B")
    src_tokens = re.findall(r"\b(NWS|NOAA|BLS|CME|NYMEX|COMEX|LME|OPM|BEA|NBER|FOMC)\b", raw, re.I)
    if len(set(t.upper() for t in src_tokens)) >= 2 and not re.search(r"primary|priority|first|governs|takes precedence", blob):
        score += 26
        flags.append("multiple sources, no stated hierarchy")

    if any(re.search(p, raw, re.I) for p in REVISION_PRONE) and not re.search(r"initial (print|release|estimate)|first (print|release)|as first (published|reported)", blob):
        score += 14
        flags.append("revision-prone source, revision rule unstated")

    return _clamp(score), flags


# ------------------------------------------------------------------ timing lever

TIME_PATTERNS = [
    r"\b\d{1,2}:\d{2}\s*(am|pm)?\s*(et|est|edt|ct|pt|utc|gmt)\b",
    r"\b(11:59|12:00|midnight|noon)\b.*\b(et|est|utc|gmt)\b",
    r"\bclose of (business|trading)\b",
    r"\bsettlement (price|time)\b",
]
DATEONLY_HINT = [r"\bas of\b", r"\bby (jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|the end)", r"\bend of (the )?(day|month|year|quarter)\b"]


def score_timing(text, title):
    blob = f"{title}\n{text}".lower()
    flags = []
    score = 16

    # Daily-observation markets (weather climate reports, daily totals) are settled on
    # a calendar-day basis. They legitimately have no intraday clock, so a missing
    # time-of-day is not a defect here.
    daily_obs = bool(re.search(r"calendar day|daily (maximum|minimum|climate|total|high|low)|nws daily", blob))
    reversible = bool(re.search(r"ceasefire|shutdown|agreement|truce|deal|resign|step down", blob))
    revision = any(re.search(p, blob) for p in REVISION_PRONE)
    if daily_obs and not reversible and not revision:
        return _clamp(12), flags

    has_time = any(re.search(p, blob, re.I) for p in TIME_PATTERNS)
    has_tz = bool(re.search(r"\b(et|est|edt|ct|cst|pt|pst|utc|gmt)\b", blob))
    dateonly = any(re.search(p, blob, re.I) for p in DATEONLY_HINT)

    if has_time:
        score -= 8
    else:
        score += 20
        flags.append("no explicit settlement time")

    if not has_tz:
        score += 16
        flags.append("no timezone specified")

    if dateonly and not has_time:
        score += 20
        flags.append("date-only cutoff — 'as of' / 'by end of' is ambiguous")

    # announced-then-reversed style events (ceasefire, shutdown, agreement) need a
    # duration / snapshot rule or the clock is genuinely undefined.
    if re.search(r"ceasefire|shutdown|agreement|truce|deal|resign|step down", blob) and not re.search(r"remain|for at least|continuous|as of \d", blob):
        score += 18
        flags.append("reversible event, no snapshot/duration rule")

    if any(re.search(p, blob) for p in REVISION_PRONE) and not re.search(r"initial|first (print|release)", blob):
        score += 22
        flags.append("initial vs revised print not specified")

    return _clamp(score), flags


# -------------------------------------------------------------- definition lever

INTERPRETIVE_TERMS = [
    "ceasefire", "recession", "war", "crisis", "significant", "substantial",
    "meaningful", "major", "credible", "reasonable", "effectively", "de facto",
    "peace", "truce", "collapse", "success", "failure", "victory", "defeat",
]
VERIFIABLE_SIGNALS = [
    r">=|<=|>|<", r"\bat or (above|below)\b", r"\babove\b", r"\bbelow\b",
    r"\bat least\b", r"\bexactly\b", r"\bequal to\b",
    r"\d+(\.\d+)?\s*(%|percent|degrees?|inch|inches|bps|basis points|\$)",
    r"\$\s?\d", r"\b\d{2,}\b",
]


def score_definition(text, title, subtitle=""):
    blob = f"{title}\n{subtitle}\n{text}".lower()
    flags = []
    score = 20

    interp_hits = [t for t in INTERPRETIVE_TERMS if re.search(rf"\b{re.escape(t)}\b", blob)]
    verifiable = any(re.search(p, blob, re.I) for p in VERIFIABLE_SIGNALS)

    if interp_hits:
        score += min(60, 22 + 12 * len(interp_hits))
        flags.append(f"interpretive term(s): {', '.join(interp_hits[:3])}")

    if verifiable:
        score -= 16
    else:
        score += 18
        flags.append("no numeric / objectively verifiable threshold")

    # ambiguous inequality direction
    if re.search(r"\babove\b", blob) and not re.search(r"at or above|>=|inclusive|exclusive", blob):
        score += 6
        flags.append("'above' — inclusive vs exclusive not stated")

    # compound conditions widen the surface for dispute
    if re.search(r"\band\b.*\band\b", blob) or (re.search(r"\bboth\b", blob) and re.search(r"\band\b", blob)):
        score += 10
        flags.append("compound condition (multiple clauses)")

    # 'narrower than headline' proxy: subtitle materially qualifies the title
    if subtitle and len(subtitle) > 12 and not _subset_words(subtitle, title):
        score += 10
        flags.append("subtitle narrows the headline question")

    return _clamp(score), flags


# ------------------------------------------------------------------- composition

def analyze(market, policy):
    """Score one market dict. Returns the full integrity report."""
    text = " ".join(str(market.get(k, "")) for k in ("rules_primary", "rules_secondary"))
    title = market.get("title", "")
    subtitle = market.get("subtitle", "")

    s_src, f_src = score_source(text, title)
    s_tim, f_tim = score_timing(text, title)
    s_def, f_def = score_definition(text, title, subtitle)

    w = policy["weights"]
    composite = round(w["source"] * s_src + w["timing"] * s_tim + w["definition"] * s_def)
    verdict = verdict_of(composite, policy)

    return {
        "ticker": market.get("ticker"),
        "title": title,
        "subtitle": subtitle,
        "category": market.get("category", "uncategorized"),
        "open_interest": market.get("open_interest", 0),
        "rules_primary": market.get("rules_primary", ""),
        "levers": {
            "source": {"score": s_src, "flags": f_src,
                       "question": "is there one authoritative, timely source?"},
            "timing": {"score": s_tim, "flags": f_tim,
                       "question": "is the settlement clock exact?"},
            "definition": {"score": s_def, "flags": f_def,
                           "question": "does the question map to a verifiable fact?"},
        },
        "composite": composite,
        "verdict": verdict,
        "policy_version": policy["version"],
    }


def verdict_of(composite, policy):
    t = policy["thresholds"]
    if composite <= t["clean"]:
        return {"key": "clean", "label": "AUTO-RESOLVE", "note": "resolves clean"}
    if composite <= t["monitored"]:
        return {"key": "monitored", "label": "MONITORED", "note": "resolvable · watch"}
    return {"key": "review", "label": "HOLD — REVIEW", "note": "dispute risk"}


# -------------------------------------------------------------------- resolution

def resolve(report, source_value):
    """
    Produce an auditable resolution trail. If the market can be evaluated against a
    concrete source value (e.g. an NWS observation), compute the outcome. Otherwise,
    or if the verdict is HOLD, the trail ends held for human review — never guessed.
    """
    steps = []

    def step(act, detail, hold=False):
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
        payload = f"{report['ticker']}|{act}|{detail}|{ts}"
        sig = hashlib.sha256(payload.encode()).hexdigest()[:10]
        steps.append({"act": act, "ts": ts, "detail": detail, "sig": f"0x{sig}", "hold": hold})

    step("Criteria parsed",
         f"Levers scored — source {report['levers']['source']['score']}, "
         f"timing {report['levers']['timing']['score']}, "
         f"definition {report['levers']['definition']['score']}. Composite {report['composite']}.")

    if report["verdict"]["key"] == "review":
        step("Resolution HELD",
             "Composite exceeds the review threshold. Not auto-resolvable as written; "
             "escalated to human review before any payout.", hold=True)
        return {"outcome": "HELD", "trail": steps}

    if source_value is None:
        step("Awaiting source value",
             "Contract is clean enough to auto-resolve, but no settlement value has "
             "been observed yet. Monitoring the designated source.")
        return {"outcome": "PENDING", "trail": steps}

    # concrete evaluation (weather threshold markets, price thresholds, etc.)
    outcome = _evaluate(report["title"], source_value)
    step("Source observed",
         f"Designated source returned {source_value.get('label', source_value)}.")
    if outcome is None:
        step("Evaluation deferred",
             "Observed value does not map unambiguously to the criterion. Routed to review.",
             hold=True)
        return {"outcome": "HELD", "trail": steps}
    step(f"Auto-resolved {outcome}",
         "Condition evaluated against observed value and written to the resolution ledger.")
    return {"outcome": outcome, "trail": steps}


def _evaluate(title, source_value):
    """Very small threshold evaluator for demonstrable market types."""
    val = source_value.get("value")
    if val is None:
        return None
    m = re.search(r"(\d+(?:\.\d+)?)", title)
    if not m:
        return None
    threshold = float(m.group(1))
    above = bool(re.search(r"above|reach|at least|>=|>|exceed|more than", title, re.I))
    below = bool(re.search(r"below|under|less than|<=|<|fewer", title, re.I))
    try:
        val = float(val)
    except (TypeError, ValueError):
        return None
    if above:
        return "YES" if val >= threshold else "NO"
    if below:
        return "YES" if val <= threshold else "NO"
    return None


# ------------------------------------------------------------------------ helpers

def _clamp(n):
    return max(0, min(100, int(round(n))))


def _subset_words(a, b):
    aw = set(re.findall(r"[a-z]{4,}", a.lower()))
    bw = set(re.findall(r"[a-z]{4,}", b.lower()))
    return aw.issubset(bw) if aw else True
