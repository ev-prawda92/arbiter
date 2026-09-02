from __future__ import annotations
import re
from .schema import BenchmarkCase

TZ = re.compile(r"\b(?:ET|EST|EDT|CT|CST|CDT|MT|MST|MDT|PT|PST|PDT|UTC|GMT)\b", re.I)
AUTH = re.compile(r"\b(?:NWS|NOAA|BLS|BEA|FOMC|Federal Reserve|Associated Press|AP race call|Binance|official Tour de France (?:website|results|classification))\b", re.I)

def validate(case: BenchmarkCase) -> tuple[bool, str]:
    text = case.criteria
    fm = case.expected.failure_mode
    if fm == "NONE":
        return (bool(text.strip()), "clean parent has criteria")
    if fm == "SOURCE_MISSING":
        ok = not AUTH.search(text) and "credible news reporting" not in text.lower()
        return ok, "named authority removed and no vague substitute introduced"
    if fm == "SOURCE_VAGUE":
        ok = "credible news reporting" in text.lower() and not AUTH.search(text)
        return ok, "vague reporting language is the governing source signal"
    if fm == "TIMEZONE_MISSING":
        has_clock = bool(re.search(r"\b\d{1,2}:\d{2}\b|\b\d{1,2}\s*(?:am|pm)\b", text, re.I))
        ok = has_clock and not TZ.search(text)
        return ok, "clock remains but timezone removed"
    if fm == "SUBJECTIVE_TERM":
        ok = bool(re.search(r"\bmeaningful\b|\bsignificant\b", text, re.I))
        return ok, "subjective term planted"
    return False, "no validator"
