"""Operational workflow and advisory agent layer for Arbiter v0.8.

The workflow layer turns Arbiter's governed state into a prioritized human work
queue and a concise executive brief. It is deliberately non-binding: it may
triage, summarize, and recommend, but it never changes settlement outcomes.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any


def _stable_id(kind: str, subject: str) -> str:
    raw = f"{kind}|{subject}".encode()
    return "work_" + hashlib.sha256(raw).hexdigest()[:14]


def _money(v: float) -> str:
    return f"${v/1e6:.1f}M"


def build_work_queue(
    reports: list[dict],
    portfolio: dict,
    infrastructure: dict,
    work_states: dict[str, dict] | None = None,
) -> dict[str, Any]:
    """Derive a prioritized queue from deterministic Arbiter state."""
    work_states = work_states or {}
    items: list[dict[str, Any]] = []

    def add(kind: str, subject: str, title: str, detail: str, severity: str,
            owner_role: str, action: str, notional: float = 0, href: str = ""):
        item_id = _stable_id(kind, subject)
        persisted = work_states.get(item_id, {})
        status = persisted.get("status", "open")
        if status == "resolved":
            # Keep resolved work discoverable in the payload, but later sorting
            # ensures active work remains the operational focus.
            pass
        items.append({
            "id": item_id,
            "kind": kind,
            "subject": subject,
            "title": title,
            "detail": detail,
            "severity": severity,
            "owner_role": owner_role,
            "recommended_action": action,
            "notional": float(notional or 0),
            "href": href,
            "status": status,
            "owner": persisted.get("owner", ""),
            "note": persisted.get("note", ""),
            "updated_at": persisted.get("updated_at"),
        })

    for r in reports:
        verdict = r.get("verdict", {}).get("key")
        ticker = r.get("ticker", "unknown")
        oi = float(r.get("open_interest", 0) or 0)
        levers = r.get("levers", {})
        if verdict == "review":
            add(
                "resolution_hold", ticker,
                f"Resolve HOLD: {ticker}",
                r.get("title", "Contract is held for review."),
                "critical" if oi >= 5_000_000 else "high",
                "Compliance / Resolution Ops",
                "Review the governing terms, approved authority, and evidence before payout authorization.",
                oi, f"/resolution/{ticker}",
            )
        elif verdict == "monitored":
            dominant = max(("source", "timing", "definition"), key=lambda k: levers.get(k, {}).get("score", 0))
            flags = levers.get(dominant, {}).get("flags", [])
            add(
                "monitored_contract", ticker,
                f"Monitor {ticker}: {dominant} risk",
                flags[0] if flags else r.get("title", "Contract requires monitoring."),
                "medium",
                "Market Ops",
                f"Confirm {dominant} semantics before the resolution window closes.",
                oi, f"/resolution/{ticker}",
            )

    # Governed source health / status creates operational work independent of a
    # specific market report.
    for authority in infrastructure.get("authorities", []) or []:
        status = authority.get("status", "approved")
        if status in {"monitored", "suspended"}:
            aid = authority.get("authority_id", "unknown")
            add(
                "authority_status", aid,
                f"Authority {status}: {aid}",
                f"{authority.get('name', aid)} is currently {status}.",
                "critical" if status == "suspended" else "high",
                "Compliance / Data Ops",
                "Assess contracts dependent on this authority and confirm fallback/precedence rules.",
            )

    audit_chain = infrastructure.get("audit_chain") or {}
    if audit_chain.get("ok") is False:
        add(
            "audit_integrity", "audit_chain",
            "Audit-chain integrity requires review",
            audit_chain.get("reason", "The control-plane audit chain did not verify."),
            "critical", "Compliance / Engineering",
            "Stop automated payout authorization until audit integrity is restored and the break is explained.",
        )

    # Data-plane gaps from the persistent control store.
    if infrastructure.get("contracts", 0) and infrastructure.get("evidence_records", 0) == 0:
        add(
            "evidence_gap", "persistent_registry",
            "Registered contracts have no captured evidence",
            "The persistent contract registry contains contracts but the evidence ledger is empty.",
            "high", "Resolution Ops",
            "Connect or ingest authoritative evidence before those contracts enter settlement.",
        )

    order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    status_order = {"open": 0, "in_progress": 1, "resolved": 2}
    items.sort(key=lambda x: (status_order.get(x["status"], 0), order.get(x["severity"], 9), -x["notional"]))

    active = [i for i in items if i["status"] != "resolved"]
    totals = {
        "active": len(active),
        "critical": sum(i["severity"] == "critical" for i in active),
        "high": sum(i["severity"] == "high" for i in active),
        "in_progress": sum(i["status"] == "in_progress" for i in active),
        "notional": sum(i["notional"] for i in active),
    }
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": totals,
        "items": items,
        "boundary": "Work Queue prioritization is advisory. Humans remain responsible for governed exceptions and settlement authorization.",
    }


def build_agent_brief(queue: dict, executive: dict) -> dict[str, Any]:
    """Produce a concise, deterministic daily brief from Arbiter state.

    This is intentionally model-free in v0.8 so every sentence is traceable to
    underlying metrics. A language model can later rewrite/explain the same
    facts without becoming a settlement authority.
    """
    shared = executive.get("shared", {})
    active = [i for i in queue.get("items", []) if i.get("status") != "resolved"]
    urgent = [i for i in active if i.get("severity") in {"critical", "high"}]
    top = urgent[:3] or active[:3]

    if not active:
        headline = "No active resolution exceptions require operator attention."
    else:
        headline = f"{len(active)} item(s) require attention; {len(urgent)} are high priority or critical."

    narrative = [
        headline,
        f"{_money(float(shared.get('resolution_risk_notional', 0) or 0))} of notional carries identified resolution risk.",
        f"{_money(float(shared.get('held_notional', 0) or 0))} is currently held before payout.",
        f"{str(shared.get('primary_risk_driver', 'none')).title()} is the primary portfolio risk driver.",
    ]
    if shared.get("audit_chain_ok") is True:
        narrative.append("The Arbiter audit chain verifies.")
    elif shared.get("audit_chain_ok") is False:
        narrative.append("Audit-chain integrity requires immediate review.")

    return {
        "agent": "Arbiter Resolution Operations Agent",
        "version": "0.1",
        "mode": "advisory_non_binding",
        "headline": headline,
        "brief": narrative,
        "top_actions": [{
            "id": i["id"], "title": i["title"], "severity": i["severity"],
            "recommended_action": i["recommended_action"], "notional": i["notional"],
        } for i in top],
        "learning_signal": "Operator ownership, status changes, notes, overrides, and final dispositions are retained as feedback for future triage/evaluation improvements.",
        "boundary": "The agent summarizes and prioritizes. It cannot alter contract terms, evidence, policy, resolution outcomes, or payout authorization.",
    }


def build_overview(executive: dict, queue: dict, agent_brief: dict) -> dict[str, Any]:
    shared = executive.get("shared", {})
    return {
        "health": {
            "posture": shared.get("portfolio_posture", "unknown"),
            "total_notional": shared.get("total_notional", 0),
            "resolution_risk_notional": shared.get("resolution_risk_notional", 0),
            "held_notional": shared.get("held_notional", 0),
            "held_contracts": shared.get("held_contracts", 0),
            "monitored_contracts": shared.get("monitored_contracts", 0),
            "primary_risk_driver": shared.get("primary_risk_driver", "none"),
            "audit_chain_ok": shared.get("audit_chain_ok"),
        },
        "attention": queue.get("summary", {}),
        "agent_brief": agent_brief,
        "top_risks": executive.get("top_risks", [])[:5],
        "boundary": "Executive Overview is read-only and is derived from governed Arbiter state.",
    }
