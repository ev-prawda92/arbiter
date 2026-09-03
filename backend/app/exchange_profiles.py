"""Exchange integration profiles.

Arbiter owns the resolution-control record. The external platform retains the final
settlement authority appropriate to its operating model.
"""
from __future__ import annotations

PROFILES = {
    "generic": {
        "id": "generic",
        "name": "Generic Event-Contract Venue",
        "settlement_authority": "venue-defined",
        "arbiter_role": "resolution control, evidence governance, deterministic decision support, audit",
        "terminal_action": "produce governed resolution decision or hold for venue workflow",
    },
    "kalshi_dcm": {
        "id": "kalshi_dcm",
        "name": "CFTC-Regulated DCM Pattern (Kalshi-style)",
        "settlement_authority": "exchange rules and governed exchange settlement process",
        "arbiter_role": "pre-listing rule control, source/timing/definition governance, evidence capture, resolution controls, approvals, audit",
        "terminal_action": "prepare or authorize exchange settlement only under configured exchange controls",
        "regulatory_boundary": "Arbiter supports exchange controls and records; it does not itself confer CFTC compliance.",
    },
    "polymarket_uma": {
        "id": "polymarket_uma",
        "name": "Optimistic Oracle Pattern (Polymarket/UMA-style)",
        "settlement_authority": "UMA optimistic-oracle / smart-contract resolution process",
        "arbiter_role": "rule compilation, source/timing/definition governance, evidence packages, proposal recommendation, dispute triage, audit",
        "terminal_action": "produce a governed proposal/dispute recommendation and evidence packet; finality remains with the oracle/smart contract",
        "oracle_boundary": "Arbiter must not represent itself as replacing UMA finality for markets governed by UMA.",
    },
}


def get_profile(profile_id: str | None) -> dict:
    pid = (profile_id or "generic").strip().lower()
    return dict(PROFILES.get(pid, PROFILES["generic"]))


def list_profiles() -> list[dict]:
    return [dict(v) for v in PROFILES.values()]


def integration_boundary(profile_id: str | None, compiler_status: str, resolution_outcome: str) -> dict:
    profile = get_profile(profile_id)
    if compiler_status in {"BLOCK", "REVIEW"}:
        action = "hold_and_route_to_governed_review"
    elif resolution_outcome == "PENDING":
        action = "monitor_authoritative_evidence"
    elif profile["id"] == "polymarket_uma":
        action = "prepare_oracle_proposal_or_dispute_packet"
    else:
        action = "prepare_exchange_resolution_authorization"
    return {
        "exchange_profile": profile["id"],
        "settlement_authority": profile["settlement_authority"],
        "arbiter_terminal_action": action,
        "terminal_boundary": profile["terminal_action"],
    }
