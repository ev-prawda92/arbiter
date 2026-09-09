"""Public-API collectors for real, already-resolved event contracts.

Network collection is deliberately separate from freezing. A collector result is
only a *candidate*. A candidate becomes a benchmark case only after the freeze
step validates, deterministically samples, strips labels from inputs, and hashes
all benchmark artifacts.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Iterable

from .hashing import canonical_json, sha256_text

USER_AGENT = "Arbiter-Holdout-Collector/0.27 (+benchmark-research)"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _fetch_json(url: str, timeout: int = 30) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:400]
        raise RuntimeError(f"HTTP {exc.code} from {url}: {body}") from exc


def _query(base: str, params: dict[str, Any]) -> str:
    clean = {k: v for k, v in params.items() if v not in (None, "", [])}
    return base + "?" + urllib.parse.urlencode(clean, doseq=True)


def _case_id(venue: str, external_id: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in external_id).strip("-")
    return f"{venue.lower()}-{safe}"[:160]


def normalize_kalshi_market(raw: dict[str, Any], source_url: str, collected_at: str | None = None) -> dict[str, Any] | None:
    result = str(raw.get("result") or "").strip().upper()
    if result not in {"YES", "NO"}:
        return None
    ticker = str(raw.get("ticker") or "").strip()
    title = str(raw.get("title") or raw.get("subtitle") or "").strip()
    rules_primary = str(raw.get("rules_primary") or "").strip()
    rules_secondary = str(raw.get("rules_secondary") or "").strip()
    rules = "\n\n".join(x for x in [rules_primary, rules_secondary] if x)
    if not ticker or not title or not rules:
        return None
    raw_hash = sha256_text(canonical_json(raw))
    return {
        "case_id": _case_id("kalshi", ticker),
        "venue": "kalshi",
        "external_market_id": ticker,
        "event_id": raw.get("event_ticker"),
        "title": title,
        "rules": rules,
        "known_outcome": result,
        "settlement_value": raw.get("settlement_value_dollars") or raw.get("expiration_value"),
        "resolution_source": None,
        "category": raw.get("category") or raw.get("series_ticker") or "uncategorized",
        "opened_at": raw.get("open_time"),
        "closed_at": raw.get("close_time"),
        "settled_at": raw.get("settlement_ts"),
        "source_url": source_url,
        "collected_at": collected_at or _now(),
        "raw_sha256": raw_hash,
        "metadata": {
            "market_type": raw.get("market_type"),
            "strike_type": raw.get("strike_type"),
            "floor_strike": raw.get("floor_strike"),
            "cap_strike": raw.get("cap_strike"),
            "is_provisional": raw.get("is_provisional"),
        },
    }


def _parse_jsonish(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []
    return []


def normalize_polymarket_market(raw: dict[str, Any], source_url: str, collected_at: str | None = None) -> dict[str, Any] | None:
    if raw.get("closed") is not True:
        return None
    status = str(raw.get("umaResolutionStatus") or raw.get("uma_resolution_status") or "").strip().lower()
    if status and status not in {"resolved", "finalized", "settled"}:
        return None
    outcomes = [str(x) for x in _parse_jsonish(raw.get("outcomes"))]
    prices_raw = _parse_jsonish(raw.get("outcomePrices"))
    if len(outcomes) != 2 or len(prices_raw) != 2:
        return None
    try:
        prices = [float(x) for x in prices_raw]
    except (TypeError, ValueError):
        return None
    winner_indices = [i for i, price in enumerate(prices) if price >= 0.99]
    loser_indices = [i for i, price in enumerate(prices) if price <= 0.01]
    if len(winner_indices) != 1 or len(loser_indices) != 1:
        return None
    winner = outcomes[winner_indices[0]].strip()
    if winner.lower() not in {"yes", "no"}:
        return None
    market_id = str(raw.get("id") or raw.get("conditionId") or raw.get("slug") or "").strip()
    title = str(raw.get("question") or "").strip()
    description = str(raw.get("description") or "").strip()
    resolution_source = str(raw.get("resolutionSource") or "").strip()
    rules = description
    if resolution_source and resolution_source.lower() not in description.lower():
        rules = (rules + "\n\nResolution source: " + resolution_source).strip()
    if not market_id or not title or not rules:
        return None
    raw_hash = sha256_text(canonical_json(raw))
    return {
        "case_id": _case_id("polymarket", market_id),
        "venue": "polymarket",
        "external_market_id": market_id,
        "event_id": raw.get("eventId") or raw.get("event_id"),
        "title": title,
        "rules": rules,
        "known_outcome": winner.upper(),
        "settlement_value": None,
        "resolution_source": resolution_source or None,
        "category": raw.get("category") or "uncategorized",
        "opened_at": raw.get("startDate") or raw.get("startDateIso"),
        "closed_at": raw.get("closedTime") or raw.get("endDate") or raw.get("endDateIso"),
        "settled_at": raw.get("umaEndDate") or raw.get("umaEndDateIso") or raw.get("closedTime"),
        "source_url": source_url,
        "collected_at": collected_at or _now(),
        "raw_sha256": raw_hash,
        "metadata": {
            "slug": raw.get("slug"),
            "condition_id": raw.get("conditionId"),
            "resolved_by": raw.get("resolvedBy"),
            "uma_resolution_status": raw.get("umaResolutionStatus"),
            "market_type": raw.get("marketType"),
        },
    }


def collect_kalshi(limit: int = 100, include_historical: bool = True, sleep_seconds: float = 0.0) -> list[dict[str, Any]]:
    """Collect recent and historical settled binary Kalshi markets.

    Kalshi documents unauthenticated public market endpoints at
    https://external-api.kalshi.com/trade-api/v2/markets and
    /historical/markets. The collector uses cursor pagination and keeps only
    rows with a binary YES/NO result and non-empty rules.
    """
    bases = [
        ("https://external-api.kalshi.com/trade-api/v2/markets", {"status": "settled"}),
    ]
    if include_historical:
        bases.append(("https://external-api.kalshi.com/trade-api/v2/historical/markets", {}))
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for base, extra in bases:
        cursor = ""
        while len(out) < limit:
            page_limit = min(1000, max(1, limit - len(out)))
            url = _query(base, {**extra, "limit": page_limit, "cursor": cursor or None})
            payload = _fetch_json(url)
            markets = payload.get("markets", []) if isinstance(payload, dict) else []
            if not markets:
                break
            now = _now()
            for raw in markets:
                row = normalize_kalshi_market(raw, url, now)
                if row and row["external_market_id"] not in seen:
                    seen.add(row["external_market_id"])
                    out.append(row)
                    if len(out) >= limit:
                        break
            cursor = str(payload.get("cursor") or "") if isinstance(payload, dict) else ""
            if not cursor:
                break
            if sleep_seconds:
                time.sleep(sleep_seconds)
        if len(out) >= limit:
            break
    return out[:limit]


def collect_polymarket(limit: int = 100, sleep_seconds: float = 0.0) -> list[dict[str, Any]]:
    """Collect closed, resolved binary Polymarket markets from Gamma API."""
    base = "https://gamma-api.polymarket.com/markets"
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    offset = 0
    # Closed lists can contain non-binary/unfinished rows, so permit a bounded
    # over-fetch while still respecting the caller's requested case count.
    max_pages = max(5, (limit // 100 + 1) * 8)
    for _ in range(max_pages):
        page_limit = min(100, max(20, limit - len(out)))
        url = _query(base, {"closed": "true", "limit": page_limit, "offset": offset, "order": "closedTime", "ascending": "false"})
        payload = _fetch_json(url)
        markets = payload if isinstance(payload, list) else payload.get("markets", []) if isinstance(payload, dict) else []
        if not markets:
            break
        now = _now()
        for raw in markets:
            row = normalize_polymarket_market(raw, url, now)
            if row and row["external_market_id"] not in seen:
                seen.add(row["external_market_id"])
                out.append(row)
                if len(out) >= limit:
                    return out[:limit]
        offset += len(markets)
        if sleep_seconds:
            time.sleep(sleep_seconds)
    return out[:limit]


def dedupe_candidates(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    chosen: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        key = (str(row.get("venue") or ""), str(row.get("external_market_id") or ""))
        if not all(key):
            continue
        chosen.setdefault(key, row)
    return list(chosen.values())
