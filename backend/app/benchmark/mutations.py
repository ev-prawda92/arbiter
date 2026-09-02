from __future__ import annotations
import re
from .schema import BenchmarkCase, Expected

AUTH_NAMES = [
    r"National Weather Service", r"\bNWS\b", r"\bNOAA\b",
    r"Bureau of Labor Statistics", r"\bBLS\b",
    r"Bureau of Economic Analysis", r"\bBEA\b",
    r"Federal Reserve", r"\bFOMC\b", r"\bFed\b",
    r"Associated Press", r"\bAP\b",
    r"Binance(?:\s+[A-Z]+/[A-Z]+|\s+[A-Z]+[A-Z]+)?",
    r"official Tour de France (?:website|results|classification)?",
    r"Tour de France website",
]

def _compose(case: dict, *, source: str | None = None, definition: str | None = None,
             timing: str | None = None, revision: str | None = None) -> tuple[str, str]:
    q = case.get("title", "")
    parts = [
        definition if definition is not None else case.get("definition", ""),
        timing if timing is not None else case.get("timing", ""),
        source if source is not None else case.get("source", ""),
        revision if revision is not None else case.get("revision_rule", ""),
    ]
    return q, " ".join(x.strip() for x in parts if x and x.strip())

def _erase_authorities(text: str) -> str:
    for pat in AUTH_NAMES:
        text = re.sub(pat, "the settlement source", text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip()

def clean_parent(case: dict) -> BenchmarkCase:
    q, c = _compose(case)
    return BenchmarkCase(case["id"], None, "gold_clean", q, c,
                         Expected("none", "NONE", True),
                         {"venue": case.get("venue"), "domain": case.get("domain")})

def source_missing(case: dict) -> BenchmarkCase:
    # Remove the designated-source sentence and neutralize incidental authority names
    # elsewhere, so the planted defect is truly "no authoritative source designated".
    q, c = _compose(case, source="")
    q = _erase_authorities(q)
    c = _erase_authorities(c)
    return BenchmarkCase(case["id"]+"-M-SRCMISS", case["id"], "mutation", q, c,
                         Expected("source", "SOURCE_MISSING", False),
                         {"mutation": "remove_source"})

def source_vague(case: dict) -> BenchmarkCase:
    q, c = _compose(case, source="Resolution will use credible news reporting and reputable media sources.")
    # Neutralize authority names elsewhere so the vague source is the governing signal.
    q = _erase_authorities(q)
    c = _erase_authorities(c)
    return BenchmarkCase(case["id"]+"-M-SRCVAGUE", case["id"], "mutation", q, c,
                         Expected("source", "SOURCE_VAGUE", False),
                         {"mutation": "vague_source"})

def timezone_missing(case: dict) -> BenchmarkCase | None:
    q, c = _compose(case)
    if not re.search(r"\b(?:ET|EST|EDT|CT|CST|CDT|MT|MST|MDT|PT|PST|PDT|UTC|GMT)\b", c):
        return None
    mutated = re.sub(r"\b(?:ET|EST|EDT|CT|CST|CDT|MT|MST|MDT|PT|PST|PDT|UTC|GMT)\b", "", c)
    return BenchmarkCase(case["id"]+"-M-TZMISS", case["id"], "mutation", q,
                         re.sub(r"\s+", " ", mutated).strip(),
                         Expected("timing", "TIMEZONE_MISSING", False),
                         {"mutation": "remove_timezone"})

def subjective_definition(case: dict) -> BenchmarkCase:
    q, c = _compose(case, definition="A meaningful or significant version of the described event occurs.")
    return BenchmarkCase(case["id"]+"-M-SUBJ", case["id"], "mutation", q, c,
                         Expected("definition", "SUBJECTIVE_TERM", False),
                         {"mutation": "subjective_definition"})

GENERATORS = [source_missing, source_vague, timezone_missing, subjective_definition]
