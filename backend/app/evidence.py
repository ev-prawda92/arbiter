"""Evidence packet builder for Arbiter v0.4.

Produces a stable, portable audit artifact from the contract, governed policy,
observed source value, and deterministic resolution trail.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone


def build_packet(report: dict, resolution: dict, source_value=None) -> dict:
    packet = {
        "schema": "arbiter.evidence.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "contract": {
            "ticker": report.get("ticker"),
            "title": report.get("title"),
            "category": report.get("category"),
            "rules_primary": report.get("rules_primary", ""),
        },
        "authorities": {
            "contract_authority": "published event-contract resolution terms",
            "resolution_authority": (source_value or {}).get("source") if isinstance(source_value, dict) else None,
            "governance_authority": f"Arbiter policy {report.get('policy_version')}",
        },
        "integrity": {
            "levers": report.get("levers"),
            "composite": report.get("composite"),
            "verdict": report.get("verdict"),
        },
        "evidence": source_value,
        "resolution": resolution,
    }
    canonical = json.dumps(packet, sort_keys=True, separators=(",", ":"), default=str).encode()
    packet["packet_hash"] = "sha256:" + hashlib.sha256(canonical).hexdigest()
    return packet
