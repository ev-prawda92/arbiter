"""Arbiter v0.36 live venue intake.

Pulls watched markets from Kalshi and Polymarket, open or settled, and turns
them into governed state the rest of Arbiter already understands:

  * one contract per market (versioned when the venue's rules text changes);
  * evidence records hashed from the full venue API response, appended only
    when something that matters changes (status, outcome, rules, disputes) -
    not on every price tick;
  * a work item in the queue for any market that needs a human judgment,
    routed by the deterministic hardness classifier, grouped per watched
    event so dual-listed markets form one work pattern.

Re-syncing is idempotent and never reopens work: once a work item exists its
workflow state belongs to operators and governed decisions, not to the sync.
A settled market closes its own intake work item with the venue's outcome.

Network access is injected (``fetcher``) so the whole pipeline runs offline
against fixtures in CI; the default fetcher calls the public venue APIs.
"""
from __future__ import annotations

import hashlib
import json
import urllib.parse
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from .active_evidence import get_service as get_evidence_service
from .real_benchmark.collectors import KALSHI_HOSTS, _fetch_json, _parse_jsonish, _uma_dispute_count
from .real_benchmark.hardness import classify_candidate
from .resolution_infra import (
    Authority,
    EvidenceRecord,
    ResolutionSpecification,
    ResolutionStore,
    canonical_hash,
    gen_id,
    utcnow,
)

VERSION = "0.36.0"
ACTOR = "system:venue-intake"
PARSER_VERSION = f"venue-intake-{VERSION}"

VENUE_AUTHORITIES = {
    "kalshi": ("auth_kalshi_rules", "Kalshi contract terms", "Kalshi"),
    "polymarket": ("auth_polymarket_rules", "Polymarket market rules", "Polymarket"),
}

# Hardness class -> (work-item kind, severity, action template). The kinds map
# onto blockers operations_intelligence already knows, so governed decisions
# can clear them (v0.35) wherever the blocker is a judgment call.
ROUTING = {
    "disputed": ("policy_review", "high", "Record the governing interpretation for: {label}"),
    "interpretive_criteria": ("policy_review", "high", "Record the governing interpretation for: {label}"),
    "multi_source_conflict": ("authority_conflict", "high", "Record which source controls for: {label}"),
    "revised_source": ("timing_revision", "medium", "Confirm whether the initial or revised release controls for: {label}"),
    "late_or_void": ("operator_review", "medium", "Review the late or void settlement for: {label}"),
}
CROSS_VENUE_KIND = "evidence_conflict"

Fetcher = Callable[[str, str], tuple[dict[str, Any], str]]


# --------------------------------------------------------------------------
# fetch + normalize
# --------------------------------------------------------------------------

def fetch_live(venue: str, market_id: str) -> tuple[dict[str, Any], str]:
    """Fetch one market's raw JSON from the public venue API."""
    if venue == "kalshi":
        last_error: Exception | None = None
        for host in KALSHI_HOSTS:
            url = f"{host}/trade-api/v2/markets/{urllib.parse.quote(market_id)}"
            try:
                payload = _fetch_json(url)
            except RuntimeError as exc:  # not on this host -> try the next
                last_error = exc
                continue
            market = payload.get("market") if isinstance(payload, dict) else None
            if isinstance(market, dict):
                return market, url
        raise LookupError(f"kalshi market {market_id} not found on any host ({last_error})")
    if venue == "polymarket":
        if market_id.isdigit():
            url = f"https://gamma-api.polymarket.com/markets/{market_id}"
            payload = _fetch_json(url)
            market = payload if isinstance(payload, dict) else None
        else:
            url = "https://gamma-api.polymarket.com/markets?" + urllib.parse.urlencode({"slug": market_id})
            payload = _fetch_json(url)
            rows = payload if isinstance(payload, list) else (payload or {}).get("markets", [])
            market = rows[0] if rows else None
        if not isinstance(market, dict):
            raise LookupError(f"polymarket market {market_id} not found")
        return market, url
    raise ValueError(f"unsupported venue: {venue}")


def normalize(venue: str, raw: dict[str, Any], url: str) -> dict[str, Any]:
    """Normalize an open OR settled market into one row shape."""
    if venue == "kalshi":
        market_id = str(raw.get("ticker") or "").strip()
        rules = "\n\n".join(x for x in (str(raw.get("rules_primary") or "").strip(),
                                        str(raw.get("rules_secondary") or "").strip()) if x)
        result = str(raw.get("result") or "").strip().upper()
        status = str(raw.get("status") or "").strip().lower()
        outcome = result if result in {"YES", "NO"} else None
        settled = outcome is not None or status in {"settled", "finalized"}
        return {
            "venue": "kalshi", "market_id": market_id, "event_id": raw.get("event_ticker"),
            "title": str(raw.get("title") or raw.get("subtitle") or "").strip(), "rules": rules,
            "status": "settled" if settled else ("closed" if status in {"closed", "determined"} else "open"),
            "outcome": outcome, "closed_at": raw.get("close_time"), "settled_at": raw.get("settlement_ts"),
            "dispute_count": 0, "source_url": url,
        }
    if venue == "polymarket":
        market_id = str(raw.get("id") or raw.get("slug") or "").strip()
        description = str(raw.get("description") or "").strip()
        source = str(raw.get("resolutionSource") or "").strip()
        rules = description
        if source and source.lower() not in description.lower():
            rules = (rules + "\n\nResolution source: " + source).strip()
        outcome = None
        uma = str(raw.get("umaResolutionStatus") or "").strip().lower()
        if raw.get("closed") is True and uma in {"", "resolved", "finalized", "settled"}:
            outcomes = [str(x) for x in _parse_jsonish(raw.get("outcomes"))]
            try:
                prices = [float(x) for x in _parse_jsonish(raw.get("outcomePrices"))]
            except (TypeError, ValueError):
                prices = []
            if len(outcomes) == 2 and len(prices) == 2:
                winners = [o for o, p in zip(outcomes, prices) if p >= 0.99]
                if len(winners) == 1 and winners[0].strip().upper() in {"YES", "NO"}:
                    outcome = winners[0].strip().upper()
        settled = outcome is not None
        return {
            "venue": "polymarket", "market_id": market_id, "event_id": raw.get("eventId"),
            "title": str(raw.get("question") or "").strip(), "rules": rules,
            "status": "settled" if settled else ("closed" if raw.get("closed") is True else "open"),
            "outcome": outcome, "closed_at": raw.get("closedTime") or raw.get("endDate"),
            "settled_at": raw.get("umaEndDate") or raw.get("closedTime"),
            "dispute_count": _uma_dispute_count(raw), "source_url": url,
        }
    raise ValueError(f"unsupported venue: {venue}")


def classify(row: dict[str, Any]) -> dict[str, Any]:
    """Run the deterministic hardness classifier on a live row."""
    return classify_candidate({
        "case_id": f"{row['venue']}-{row['market_id']}", "venue": row["venue"],
        "title": row["title"], "rules": row["rules"],
        "known_outcome": row.get("outcome") or "",
        "closed_at": row.get("closed_at"), "settled_at": row.get("settled_at"),
        "metadata": {"uma_dispute_count": row.get("dispute_count") or 0},
    })


def review_class(verdict: dict[str, Any], override: str | None = None) -> str | None:
    """The hardness class that should put this market in front of a human, if any."""
    if override:
        return override
    primary = verdict.get("primary_class")
    if primary in ROUTING:
        return primary
    if verdict.get("interpretive_hint"):
        return "interpretive_criteria"
    return None


# --------------------------------------------------------------------------
# watchlist
# --------------------------------------------------------------------------

@dataclass
class WatchedEvent:
    event_id: str
    label: str
    markets: list[tuple[str, str]] = field(default_factory=list)  # (venue, market_id)
    review_class: str | None = None


def load_watchlist(path: str) -> list[WatchedEvent]:
    """Read a seeds JSONL file (same format as benchmarks/seeds)."""
    events: list[WatchedEvent] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            row = json.loads(line)
            markets = [("kalshi", str(t)) for t in row.get("kalshi") or [] if "TO-VERIFY" not in str(t)]
            markets += [("polymarket", str(t)) for t in row.get("polymarket") or [] if "TO-VERIFY" not in str(t)]
            if markets:
                events.append(WatchedEvent(event_id=row["seed_event_id"], label=row.get("label") or row["seed_event_id"],
                                           markets=markets, review_class=row.get("review_class")))
    return events


# --------------------------------------------------------------------------
# intake
# --------------------------------------------------------------------------

def _subject(venue: str, market_id: str) -> str:
    return f"{venue.upper()}-{market_id}"


def _ensure_authority(store: ResolutionStore, venue: str) -> str:
    aid, name, org = VENUE_AUTHORITIES[venue]
    if not store.get_authority(aid):
        store.save_authority(Authority(authority_id=aid, version=1, name=name, organization=org,
                                       source_type="venue_rules"), actor=ACTOR)
    return aid


def _ensure_contract(store: ResolutionStore, row: dict[str, Any], event: WatchedEvent, auth_id: str) -> tuple[str, int, bool]:
    contract_id = f"{row['venue']}:{row['market_id']}"
    latest = store.latest_contract(contract_id)
    definition = {"yes_if": row["rules"], "rules_sha256": canonical_hash(row["rules"])}
    if latest and latest.get("definition", {}).get("rules_sha256") == definition["rules_sha256"]:
        return contract_id, int(latest["contract_version"]), False
    version = int(latest["contract_version"]) + 1 if latest else 1
    store.save_contract(ResolutionSpecification(
        contract_id=contract_id, contract_version=version, title=row["title"] or contract_id,
        definition=definition, timing={"closed_at": row.get("closed_at"), "settled_at": row.get("settled_at")},
        authority_ids=[auth_id],
        metadata={"venue": row["venue"], "market_id": row["market_id"], "watched_event": event.event_id,
                  "source_url": row["source_url"]},
    ), actor=ACTOR, status="active")
    return contract_id, version, True


def _observed_value(row: dict[str, Any]) -> dict[str, Any]:
    """The part of a market that matters for resolution (not prices/volume)."""
    return {"venue": row["venue"], "market_id": row["market_id"], "status": row["status"],
            "outcome": row.get("outcome"), "rules_sha256": canonical_hash(row["rules"]),
            "dispute_count": row.get("dispute_count") or 0,
            "closed_at": row.get("closed_at"), "settled_at": row.get("settled_at")}


def _append_evidence_if_changed(store: ResolutionStore, contract_id: str, auth_id: str,
                                row: dict[str, Any], raw: dict[str, Any]) -> dict[str, Any] | None:
    value = _observed_value(row)
    prior = [e for e in store.list_evidence(contract_id, limit=500) if e.get("authority_id") == auth_id]
    latest = max(prior, key=lambda e: int(e.get("revision_number") or 1), default=None)
    if latest and canonical_hash(latest.get("normalized_value")) == canonical_hash(value):
        return None
    rec = EvidenceRecord(
        evidence_id=gen_id("evid"), authority_id=auth_id, authority_version=1,
        observed_at=utcnow(), retrieved_at=utcnow(), normalized_value=value,
        raw_payload_hash=canonical_hash(raw), parser_version=PARSER_VERSION, contract_id=contract_id,
        revision_number=(int(latest.get("revision_number") or 1) + 1) if latest else 1,
        supersedes=latest["evidence_id"] if latest else None, source_locator=row["source_url"],
    )
    return store.append_evidence(rec, actor=ACTOR)


def _exception_id(kind: str, subject: str) -> str:
    # Same derivation ActiveEvidenceService uses, so we can look it up.
    return "exc_" + hashlib.sha256(f"{kind}|{subject}".encode()).hexdigest()[:16]


def _open_exception_once(store: ResolutionStore, *, kind: str, subject: str, contract_id: str | None,
                         authority_id: str | None, severity: str, title: str, detail: str, action: str,
                         metadata: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    evsvc = get_evidence_service(store)
    existing = evsvc.get_exception(_exception_id(kind, subject))
    if existing:
        return existing, False  # never reopen or reset work an operator/decision owns
    exc = evsvc._upsert_exception(kind=kind, subject=subject, contract_id=contract_id, authority_id=authority_id,
                                  severity=severity, title=title, detail=detail, action=action,
                                  metadata=metadata, actor=ACTOR)
    return exc, True


def _close_exception_for_settlement(store: ResolutionStore, kind: str, subject: str, row: dict[str, Any]) -> bool:
    evsvc = get_evidence_service(store)
    exc = evsvc.get_exception(_exception_id(kind, subject))
    if not exc or exc.get("status") == "resolved":
        return False
    note = f"Venue settled {row['outcome']} ({row['venue']} {row['market_id']})."
    with store.connect() as db:
        db.execute("UPDATE evidence_exceptions SET status='resolved', updated_at=? WHERE exception_id=?",
                   (utcnow(), exc["exception_id"]))
    store.set_work_state(exc["work_item_id"], "resolved", "Resolution Ops", note, ACTOR)
    store._audit(ACTOR, "evidence.exception.resolved", "evidence_exception", exc["exception_id"],
                 {"subject": subject, "reason": "venue_settled", "outcome": row["outcome"]})
    return True


def sync(store: ResolutionStore, events: Iterable[WatchedEvent], fetcher: Fetcher = fetch_live,
         dry_run: bool = False) -> dict[str, Any]:
    """Pull every watched market and bring governed state up to date."""
    report: dict[str, Any] = {"version": VERSION, "started_at": utcnow(), "dry_run": dry_run,
                              "markets": [], "errors": [], "events": []}
    for event in events:
        rows: list[dict[str, Any]] = []
        for venue, market_id in event.markets:
            entry: dict[str, Any] = {"event": event.event_id, "venue": venue, "market_id": market_id}
            try:
                raw, url = fetcher(venue, market_id)
                row = normalize(venue, raw, url)
            except Exception as exc:  # one bad market never blocks the rest
                entry["error"] = f"{type(exc).__name__}: {exc}"
                report["errors"].append(entry)
                continue
            verdict = classify(row)
            klass = review_class(verdict, event.review_class)
            entry.update({"title": row["title"], "status": row["status"], "outcome": row.get("outcome"),
                          "hardness": verdict["primary_class"], "review_class": klass,
                          "reasons": verdict.get("reasons", {}), "raw_sha256": canonical_hash(raw)})
            rows.append(row)
            if dry_run:
                report["markets"].append(entry)
                continue

            auth_id = _ensure_authority(store, venue)
            contract_id, version, new_version = _ensure_contract(store, row, event, auth_id)
            evidence = _append_evidence_if_changed(store, contract_id, auth_id, row, raw)
            entry.update({"contract_id": contract_id, "contract_version": version,
                          "contract_version_created": new_version,
                          "evidence_id": evidence["evidence_id"] if evidence else None})

            subject = _subject(venue, market_id)
            if klass:
                kind, severity, action = ROUTING[klass]
                if row["status"] == "settled":
                    entry["work_item"] = "closed" if _close_exception_for_settlement(store, kind, subject, row) else "none (settled)"
                else:
                    reasons = "; ".join(r for rs in verdict.get("reasons", {}).values() for r in rs) or klass
                    exc, created = _open_exception_once(
                        store, kind=kind, subject=subject, contract_id=contract_id, authority_id=auth_id,
                        severity=severity, title=f"{row['title']} ({venue} {market_id})",
                        detail=f"Needs a human judgment ({klass.replace('_', ' ')}): {reasons}",
                        action=action.format(label=event.label),
                        metadata={"watched_event": event.event_id, "hardness": verdict, "source": "venue_intake"})
                    entry["work_item"] = "opened" if created else "exists"
                    entry["work_item_id"] = exc.get("work_item_id")
            else:
                entry["work_item"] = "none"
            report["markets"].append(entry)

        # Dual-listed and both settled, but the venues disagree: that is work.
        settled = {(r["venue"], r["market_id"]): r["outcome"] for r in rows if r.get("outcome")}
        venues = {v for (v, _), _o in settled.items()}
        outcomes = set(settled.values())
        summary = {"event": event.event_id, "settled": {f"{v}:{m}": o for (v, m), o in settled.items()}}
        if len(venues) >= 2 and len(outcomes) >= 2:
            summary["cross_venue"] = "disagree"
            if not dry_run:
                _open_exception_once(
                    store, kind=CROSS_VENUE_KIND, subject=f"EVENT-{event.event_id}", contract_id=None,
                    authority_id=None, severity="critical",
                    title=f"Venues disagree: {event.label}",
                    detail="Settled outcomes differ across venues: " + ", ".join(f"{k}={v}" for k, v in summary["settled"].items()),
                    action=f"Record which outcome the governing evidence supports for: {event.label}",
                    metadata={"watched_event": event.event_id, "settled": summary["settled"], "source": "venue_intake"})
        elif len(venues) >= 2:
            summary["cross_venue"] = "agree"
        report["events"].append(summary)

    report["finished_at"] = utcnow()
    report["totals"] = {
        "markets": len(report["markets"]), "errors": len(report["errors"]),
        "work_items_opened": sum(m.get("work_item") == "opened" for m in report["markets"]),
        "work_items_closed": sum(m.get("work_item") == "closed" for m in report["markets"]),
        "evidence_appended": sum(bool(m.get("evidence_id")) for m in report["markets"]),
        "contract_versions_created": sum(bool(m.get("contract_version_created")) for m in report["markets"]),
        "cross_venue_disagreements": sum(e.get("cross_venue") == "disagree" for e in report["events"]),
    }
    return report


# --------------------------------------------------------------------------
# discovery: scan currently open markets, keep the ones that need a human
# --------------------------------------------------------------------------

ListFetcher = Callable[[str, int], list[tuple[dict[str, Any], str]]]


def _is_kalshi_parlay(raw: dict[str, Any]) -> bool:
    ticker = str(raw.get("ticker") or "")
    return bool(raw.get("mve_collection_ticker")) or ticker.startswith("KXMVE")


def list_open_live(venue: str, limit: int) -> list[tuple[dict[str, Any], str]]:
    """Open markets from the public venue APIs (Kalshi: both hosts, no parlays)."""
    out: list[tuple[dict[str, Any], str]] = []
    if venue == "kalshi":
        seen: set[str] = set()
        for host in KALSHI_HOSTS:
            cursor, fetched = "", 0
            while fetched < limit:
                params = {"status": "open", "limit": min(1000, limit - fetched), "mve_filter": "exclude"}
                if cursor:
                    params["cursor"] = cursor
                url = f"{host}/trade-api/v2/markets?" + urllib.parse.urlencode(params)
                try:
                    payload = _fetch_json(url)
                except RuntimeError:
                    break
                markets = (payload.get("markets") or []) if isinstance(payload, dict) else []
                fetched += len(markets)
                for m in markets:
                    t = str(m.get("ticker") or "")
                    if t and t not in seen and not _is_kalshi_parlay(m) and str(m.get("rules_primary") or "").strip():
                        seen.add(t)
                        out.append((m, f"{host}/trade-api/v2/markets/{urllib.parse.quote(t)}"))
                cursor = (payload.get("cursor") or "") if isinstance(payload, dict) else ""
                if not cursor or not markets:
                    break
        return out
    if venue == "polymarket":
        url = "https://gamma-api.polymarket.com/markets?" + urllib.parse.urlencode(
            {"closed": "false", "active": "true", "limit": limit, "order": "volume", "ascending": "false"})
        payload = _fetch_json(url)
        rows = payload if isinstance(payload, list) else (payload or {}).get("markets", [])
        for m in rows:
            if isinstance(m, dict) and str(m.get("description") or "").strip():
                out.append((m, f"https://gamma-api.polymarket.com/markets/{m.get('id')}"))
        return out
    raise ValueError(f"unsupported venue: {venue}")


def _event_key(venue: str, raw: dict[str, Any]) -> tuple[str, str]:
    """(event id, label) used to group a venue's markets on one real-world event."""
    if venue == "kalshi":
        ev = str(raw.get("event_ticker") or raw.get("ticker"))
        return f"kalshi-{ev}", str(raw.get("title") or ev)
    events = raw.get("events") if isinstance(raw.get("events"), list) else []
    first = events[0] if events and isinstance(events[0], dict) else {}
    ev = str(first.get("id") or raw.get("eventId") or raw.get("id"))
    return f"polymarket-{ev}", str(first.get("title") or raw.get("question") or ev)


def discover(list_fetcher: ListFetcher = list_open_live, limit: int = 200,
             venues: Iterable[str] = ("kalshi", "polymarket"), include_all: bool = False,
             ) -> tuple[list[WatchedEvent], Fetcher, dict[str, Any]]:
    """Scan open markets; return watched events for the ones needing a human.

    Returns (events, fetcher, stats). The fetcher serves the already-downloaded
    raw payloads so ``sync`` does not fetch every market twice.
    """
    cache: dict[tuple[str, str], tuple[dict[str, Any], str]] = {}
    grouped: dict[str, WatchedEvent] = {}
    stats: dict[str, Any] = {"scanned": {}, "flagged": {}, "errors": {}}
    for venue in venues:
        try:
            listed = list_fetcher(venue, limit)
        except Exception as exc:  # a venue being down never blocks the other
            stats["errors"][venue] = f"{type(exc).__name__}: {exc}"
            continue
        stats["scanned"][venue] = len(listed)
        flagged = 0
        for raw, url in listed:
            if venue == "kalshi" and _is_kalshi_parlay(raw):
                continue  # auto-generated parlays have no rules of their own
            row = normalize(venue, raw, url)
            if not row["market_id"] or not row["rules"] or row["status"] == "settled":
                continue
            if not include_all and review_class(classify(row)) is None:
                continue
            flagged += 1
            cache[(venue, row["market_id"])] = (raw, url)
            key, label = _event_key(venue, raw)
            grouped.setdefault(key, WatchedEvent(event_id=key, label=label)).markets.append((venue, row["market_id"]))
        stats["flagged"][venue] = flagged

    def cached(venue: str, market_id: str) -> tuple[dict[str, Any], str]:
        if (venue, market_id) in cache:
            return cache[(venue, market_id)]
        return fetch_live(venue, market_id)

    return list(grouped.values()), cached, stats
