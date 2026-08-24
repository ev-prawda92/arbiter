"""
Data feeds.

Two kinds of feed:
  1. Market feed  — the contracts to review, with their resolution rules. Live
                    adapter targets Kalshi's public market API; falls back to bundled
                    sample markets when unreachable or unauthenticated.
  2. Source feed  — the authoritative data a clean market resolves against. Live
                    adapter targets the U.S. National Weather Service API (free, no
                    key), which lets weather markets genuinely auto-resolve.

Every live call has a short timeout and a sample fallback, so the app is fully
functional offline / in a demo, and upgrades to live data the moment it can reach
the network with the right config.
"""

import json
import os
import httpx

_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
KALSHI_BASE = os.environ.get("KALSHI_BASE", "https://api.elections.kalshi.com/trade-api/v2")
KALSHI_KEY = os.environ.get("KALSHI_API_KEY", "")
TIMEOUT = float(os.environ.get("FEED_TIMEOUT", "6"))


def _sample(name):
    with open(os.path.join(_DATA_DIR, name)) as f:
        return json.load(f)


# --------------------------------------------------------------------- markets

def get_markets(limit=40, live=True):
    """Return a list of normalized market dicts. Tries Kalshi live, falls back to sample."""
    if live:
        try:
            return _kalshi_live(limit)
        except Exception as e:  # noqa: BLE001 - any failure => graceful sample fallback
            return _tag_source(_sample("sample_markets.json"), f"sample (live failed: {type(e).__name__})")
    return _tag_source(_sample("sample_markets.json"), "sample")


def _kalshi_live(limit):
    headers = {"Accept": "application/json"}
    if KALSHI_KEY:
        headers["Authorization"] = f"Bearer {KALSHI_KEY}"
    with httpx.Client(timeout=TIMEOUT) as c:
        r = c.get(f"{KALSHI_BASE}/markets", params={"limit": limit, "status": "open"}, headers=headers)
        r.raise_for_status()
        raw = r.json().get("markets", [])
    out = []
    for m in raw:
        out.append({
            "ticker": m.get("ticker"),
            "title": m.get("title") or m.get("yes_sub_title") or "",
            "subtitle": m.get("subtitle") or m.get("yes_sub_title") or "",
            "category": m.get("category") or "uncategorized",
            "rules_primary": m.get("rules_primary") or "",
            "rules_secondary": m.get("rules_secondary") or "",
            "open_interest": _oi(m),
            "_source": "kalshi-live",
        })
    return out[:limit]


def _oi(m):
    # Kalshi exposes open_interest in contracts; scale to a notional-ish figure for display.
    oi = m.get("open_interest") or 0
    return int(oi) * 100


def _tag_source(markets, tag):
    for m in markets:
        m.setdefault("_source", tag)
    return markets


# ------------------------------------------------------------- resolution source

def get_source_value(report, live=True):
    """
    Fetch the authoritative value a clean market resolves against. Only weather
    markets have a live adapter wired here (NWS); everything else returns None,
    which the engine treats as 'pending — awaiting source', never as a guess.
    """
    cat = (report.get("category") or "").lower()
    if "weather" not in cat and "temperature" not in report.get("title", "").lower():
        # sample source values keyed by ticker, for the demo markets
        samples = _sample("sample_sources.json")
        return samples.get(report.get("ticker"))

    station = _station_for(report)
    if live and station:
        try:
            return _nws_live(station)
        except Exception:  # noqa: BLE001
            pass
    samples = _sample("sample_sources.json")
    return samples.get(report.get("ticker"))


_STATIONS = {"nyc": "KNYC", "central park": "KNYC", "chicago": "KORD", "o'hare": "KORD",
             "miami": "KMIA", "los angeles": "KLAX", "denver": "KDEN"}


def _station_for(report):
    t = (report.get("title", "") + " " + report.get("subtitle", "")).lower()
    for k, v in _STATIONS.items():
        if k in t:
            return v
    return None


def _nws_live(station):
    with httpx.Client(timeout=TIMEOUT, headers={"User-Agent": "arbiter-demo/0.1"}) as c:
        r = c.get(f"https://api.weather.gov/stations/{station}/observations/latest")
        r.raise_for_status()
        props = r.json().get("properties", {})
        temp_c = (props.get("temperature") or {}).get("value")
        if temp_c is None:
            raise ValueError("no temperature in observation")
        temp_f = round(temp_c * 9 / 5 + 32, 1)
        return {"value": temp_f, "label": f"{temp_f}\u00b0F observed at {station} (NWS live)",
                "source": "nws-live"}
