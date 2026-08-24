"""
Optional LLM triage.

The rule engine (engine.py) is the system of record. This adds a second opinion for
arbitrary pasted contract language: it asks a model to flag ambiguities, but the
result is presented as triage, never as the binding score. Requires ANTHROPIC_API_KEY
in the environment; if absent, the endpoint says so plainly instead of failing.
"""

import json
import os
import httpx

API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")

PROMPT = """You are a settlement-integrity adjudicator for a CFTC-regulated prediction market.
Assess ONE event contract for dispute risk on three levers, each 0-100 where higher = MORE
ambiguity / dispute risk:
- source: is there a single authoritative, timely settlement source (with fallback)?
- timing: is the settlement clock exact (date + time + timezone, revision handling)?
- definition: does the question map to a cleanly verifiable fact (no subjective terms,
  not narrower than its headline)?

MARKET QUESTION:
{q}

RESOLUTION CRITERIA:
{c}

Return ONLY minified JSON, no prose, no code fences, exactly these keys:
{{"source":int,"timing":int,"definition":int,"sourceFlags":[str],"timingFlags":[str],
"definitionFlags":[str],"outcome":"YES"|"NO"|"HELD","notes":str}}
Flags are short phrases (<=8 words); use [] for a clean lever."""


def available():
    return bool(API_KEY)


def triage(question, criteria):
    if not API_KEY:
        return {"error": "no_key",
                "message": "LLM triage is off. Set ANTHROPIC_API_KEY in the environment to enable it. "
                           "The rule engine still scores everything without it."}
    body = {
        "model": MODEL,
        "max_tokens": 1000,
        "messages": [{"role": "user", "content": PROMPT.format(q=question, c=criteria)}],
    }
    headers = {
        "x-api-key": API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    with httpx.Client(timeout=30) as c:
        r = c.post("https://api.anthropic.com/v1/messages", json=body, headers=headers)
        r.raise_for_status()
        data = r.json()
    text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
    text = text.replace("```json", "").replace("```", "").strip()
    a, b = text.find("{"), text.rfind("}")
    if a >= 0 and b >= 0:
        text = text[a:b + 1]
    return json.loads(text)
