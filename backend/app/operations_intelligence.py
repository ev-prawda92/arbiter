"""Arbiter v0.32 friction-reduction operations intelligence.

This module compresses a raw human work queue into prioritized, grouped,
explainable work. It is deliberately advisory and deterministic: it may rank,
cluster, summarize, and recommend an order of operations, but it cannot alter
contract terms, evidence, policy, resolution outcomes, or payout authorization.
"""
from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from typing import Any

VERSION = "0.32.0"

SEVERITY_WEIGHT = {"critical": 100, "high": 70, "medium": 40, "low": 15}
STATUS_WEIGHT = {"open": 10, "in_progress": 4, "resolved": -1000}


def _norm(value: str) -> str:
    text = str(value or "").lower().strip()
    text = re.sub(r"\b[a-z]{2,}[a-z0-9_-]*-[a-z0-9_-]{4,}\b", "<id>", text)
    text = re.sub(r"\b[0-9a-f]{7,}\b", "<hash>", text)
    text = re.sub(r"\b\d+(?:\.\d+)?\b", "<n>", text)
    text = re.sub(r"\s+", " ", text)
    return text


def _stable_cluster_id(blocker: str, signature: str) -> str:
    raw = f"{blocker}|{signature}".encode()
    return "cluster_" + hashlib.sha256(raw).hexdigest()[:12]


def _blocker(item: dict[str, Any]) -> str:
    kind = str(item.get("kind") or "").lower()
    text = " ".join(
        str(item.get(k) or "") for k in ("title", "detail", "recommended_action")
    ).lower()

    if "audit" in kind or "audit" in text:
        return "audit_integrity"
    if "authority" in kind or "precedence" in text or "governed source" in text:
        return "authority_conflict"
    if "evidence" in kind or "evidence" in text:
        if "conflict" in kind or "conflict" in text or "differs" in text:
            return "evidence_conflict"
        if any(token in text for token in ("missing", "empty", "waiting", "not yet", "ingest", "connect")):
            return "evidence_missing"
        return "evidence_review"
    if "timing" in text or "window" in text or "revision" in text or "final" in text:
        return "timing_revision"
    if "policy" in kind or "policy" in text or "definition" in text or "ambig" in text:
        return "policy_interpretation"
    if "monitor" in kind or "monitor" in text:
        return "monitoring"
    if "resolution_hold" in kind or "hold" in text:
        return "resolution_hold"
    return "operator_review"


def _priority(item: dict[str, Any]) -> int:
    severity = SEVERITY_WEIGHT.get(str(item.get("severity") or "").lower(), 25)
    status = STATUS_WEIGHT.get(str(item.get("status") or "open").lower(), 0)
    notional = float(item.get("notional") or 0)
    if notional >= 10_000_000:
        notional_weight = 35
    elif notional >= 5_000_000:
        notional_weight = 25
    elif notional >= 1_000_000:
        notional_weight = 15
    elif notional > 0:
        notional_weight = 5
    else:
        notional_weight = 0

    blocker = _blocker(item)
    blocker_weight = {
        "audit_integrity": 35,
        "authority_conflict": 25,
        "evidence_conflict": 20,
        "policy_interpretation": 18,
        "timing_revision": 14,
        "evidence_missing": 8,
        "resolution_hold": 12,
        "monitoring": 2,
        "operator_review": 5,
        "evidence_review": 8,
    }.get(blocker, 0)
    return max(0, severity + status + notional_weight + blocker_weight)


def _explicit_resolution(item: dict[str, Any]) -> str:
    value = item.get("resolution") or item.get("outcome") or item.get("verdict") or ""
    if isinstance(value, dict):
        value = value.get("key") or value.get("outcome") or value.get("status") or ""
    return str(value).upper().strip()


def _workflow_state(item: dict[str, Any], blocker: str, waiting_external: bool) -> str:
    """Map a case to a conservative operator-work state.

    READY_FOR_REVIEW is intentionally narrow. A HOLD, evidence conflict,
    authority conflict, unresolved evidence review, audit issue, or policy
    interpretation still needs investigation/judgment before it can be called
    ready. This prevents queue metrics from turning every active exception into
    'ready now'.
    """
    status = str(item.get("status") or "open").lower()
    explicit = str(item.get("workflow_state") or "").upper().strip()
    resolution = _explicit_resolution(item)

    if status == "resolved" or explicit == "RESOLVED":
        return "RESOLVED"
    if waiting_external or blocker == "monitoring":
        return "WAITING"
    if blocker == "policy_interpretation":
        return "POLICY_REVIEW"
    if resolution == "HOLD" or blocker == "resolution_hold":
        return "INVESTIGATING"
    if blocker in {
        "authority_conflict",
        "evidence_conflict",
        "evidence_review",
        "audit_integrity",
        "timing_revision",
    }:
        return "INVESTIGATING"
    if explicit in {"READY", "READY_FOR_REVIEW"}:
        return "READY_FOR_REVIEW"
    if item.get("ready_for_review") is True:
        return "READY_FOR_REVIEW"
    if blocker == "operator_review":
        return "READY_FOR_REVIEW"
    return "INVESTIGATING"


def enrich_item(item: dict[str, Any]) -> dict[str, Any]:
    blocker = _blocker(item)
    text = " ".join(str(item.get(k) or "") for k in ("title", "detail", "recommended_action")).lower()
    waiting_external = blocker == "evidence_missing" or any(
        token in text for token in ("waiting on", "not yet available", "external data", "source publication")
    )
    requires_policy = blocker == "policy_interpretation"
    workflow_state = _workflow_state(item, blocker, waiting_external)
    return {
        **item,
        "operations": {
            "priority_score": _priority(item),
            "blocker_type": blocker,
            "workflow_state": workflow_state,
            "waiting_on_external_data": workflow_state == "WAITING",
            "requires_policy_interpretation": requires_policy,
            "ready_for_review": workflow_state == "READY_FOR_REVIEW",
            "needs_investigation": workflow_state == "INVESTIGATING",
        },
    }


def _cluster_signature(item: dict[str, Any]) -> str:
    blocker = _blocker(item)
    detail = _norm(item.get("detail") or item.get("title") or "")
    action = _norm(item.get("recommended_action") or "")
    return f"{blocker}|{detail[:180]}|{action[:140]}"


def analyze_queue(queue: dict[str, Any], executive: dict[str, Any] | None = None) -> dict[str, Any]:
    executive = executive or {}
    raw_items = queue.get("items") or []
    active = [enrich_item(i) for i in raw_items if i.get("status") != "resolved"]
    active.sort(key=lambda i: (-i["operations"]["priority_score"], -float(i.get("notional") or 0), i.get("id", "")))

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in active:
        grouped[_cluster_signature(item)].append(item)

    clusters = []
    for signature, items in grouped.items():
        blocker = items[0]["operations"]["blocker_type"]
        notional = sum(float(i.get("notional") or 0) for i in items)
        priorities = [i["operations"]["priority_score"] for i in items]
        states = sorted({i["operations"]["workflow_state"] for i in items})
        clusters.append({
            "cluster_id": _stable_cluster_id(blocker, signature),
            "blocker_type": blocker,
            "count": len(items),
            "notional": notional,
            "max_priority_score": max(priorities) if priorities else 0,
            "case_ids": [i.get("id") for i in items],
            "example_title": items[0].get("title"),
            "recommended_action": items[0].get("recommended_action"),
            "owner_roles": sorted({str(i.get("owner_role") or "Resolution Ops") for i in items}),
            "workflow_states": states,
        })
    clusters.sort(key=lambda c: (-c["count"], -c["max_priority_score"], -c["notional"], c["cluster_id"]))

    ready = [i for i in active if i["operations"]["workflow_state"] == "READY_FOR_REVIEW"]
    waiting = [i for i in active if i["operations"]["workflow_state"] == "WAITING"]
    investigating = [i for i in active if i["operations"]["workflow_state"] == "INVESTIGATING"]
    policy = [i for i in active if i["operations"]["workflow_state"] == "POLICY_REVIEW"]
    high_impact = [i for i in active if float(i.get("notional") or 0) > 0][:10]

    repeated = [c for c in clusters if c["count"] >= 2]
    compressed_units = len(clusters)
    compression_ratio = round((len(active) / compressed_units), 2) if compressed_units else 1.0

    # Human decision load is cluster-first: repeated cases with the same root
    # cause should become one operator decision whenever governance permits.
    actionable_clusters = [
        c for c in clusters
        if not set(c.get("workflow_states") or []).issubset({"WAITING"})
    ]
    estimated_human_decisions = len(actionable_clusters)

    recommended_sequence = []
    for cluster in actionable_clusters[:5]:
        if cluster["count"] >= 2:
            recommended_sequence.append({
                "type": "cluster",
                "id": cluster["cluster_id"],
                "label": f"Resolve shared {cluster['blocker_type'].replace('_', ' ')} pattern",
                "case_count": cluster["count"],
                "notional": cluster["notional"],
            })
    for item in ready + investigating + policy:
        if len(recommended_sequence) >= 8:
            break
        if any(item.get("id") in (c.get("case_ids") or []) and c["count"] >= 2 for c in actionable_clusters):
            continue
        recommended_sequence.append({
            "type": "case",
            "id": item.get("id"),
            "label": item.get("title") or "Review case",
            "case_count": 1,
            "notional": float(item.get("notional") or 0),
            "workflow_state": item["operations"]["workflow_state"],
        })

    return {
        "version": VERSION,
        "mode": "advisory_non_binding",
        "summary": {
            "active_cases": len(active),
            "ready_for_review": len(ready),
            "needs_investigation": len(investigating),
            "waiting_on_external_data": len(waiting),
            "policy_interpretation": len(policy),
            "distinct_work_patterns": len(clusters),
            "repeated_patterns": len(repeated),
            "compression_ratio": compression_ratio,
            "estimated_human_decisions": estimated_human_decisions,
            "human_decisions_avoided": max(0, len(active) - estimated_human_decisions),
            "notional_represented": sum(float(i.get("notional") or 0) for i in active),
        },
        "clusters": clusters,
        "ready_cases": [{
            "id": i.get("id"),
            "title": i.get("title"),
            "priority_score": i["operations"]["priority_score"],
            "blocker_type": i["operations"]["blocker_type"],
            "notional": float(i.get("notional") or 0),
        } for i in ready[:12]],
        "investigating_cases": [{
            "id": i.get("id"),
            "title": i.get("title"),
            "priority_score": i["operations"]["priority_score"],
            "blocker_type": i["operations"]["blocker_type"],
            "notional": float(i.get("notional") or 0),
        } for i in investigating[:12]],
        "waiting_cases": [{
            "id": i.get("id"),
            "title": i.get("title"),
            "blocker_type": i["operations"]["blocker_type"],
        } for i in waiting[:12]],
        "highest_impact": [{
            "id": i.get("id"),
            "title": i.get("title"),
            "priority_score": i["operations"]["priority_score"],
            "notional": float(i.get("notional") or 0),
        } for i in high_impact],
        "recommended_sequence": recommended_sequence,
        "boundary": "Operations Intelligence prioritizes, groups, and explains work. It cannot change governed evidence, policy, resolution outcomes, or settlement authorization.",
    }
