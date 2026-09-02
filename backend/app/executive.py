"""Executive portfolio intelligence for Arbiter.

This module is read-only. It turns the same deterministic contract reports and
resolution-control state into role-specific operating views for Compliance,
Market Operations, Finance, and the executive team. It never changes a contract
outcome, policy, evidence record, or resolution run.
"""

from __future__ import annotations


def build(reports: list[dict], portfolio: dict, infrastructure: dict | None = None) -> dict:
    infrastructure = infrastructure or {}
    summary = portfolio.get("summary", {})
    counts = summary.get("counts", {})
    notional = summary.get("notional", {})
    total_notional = float(summary.get("total_notional", 0) or 0)
    monitored_notional = float(notional.get("monitored", 0) or 0)
    held_notional = float(summary.get("held_notional", 0) or 0)
    exposed_notional = monitored_notional + held_notional

    top_risks = portfolio.get("top_risks", [])
    pressure = portfolio.get("lever_pressure", {})
    primary_driver = pressure.get("primary_driver", "none")
    gaps = portfolio.get("coverage_gaps", [])

    held = [r for r in reports if r.get("verdict", {}).get("key") == "review"]
    monitored = [r for r in reports if r.get("verdict", {}).get("key") == "monitored"]

    def pct(v: float) -> float:
        return round(100 * v / total_notional, 1) if total_notional else 0.0

    posture = "controlled"
    if held_notional > 0:
        posture = "attention"
    if total_notional and held_notional / total_notional >= 0.20:
        posture = "elevated"

    shared = {
        "portfolio_posture": posture,
        "contracts_reviewed": int(summary.get("reviewed", len(reports)) or 0),
        "total_notional": total_notional,
        "clean_notional": float(notional.get("clean", 0) or 0),
        "monitored_notional": monitored_notional,
        "held_notional": held_notional,
        "resolution_risk_notional": exposed_notional,
        "resolution_risk_pct": pct(exposed_notional),
        "held_pct": pct(held_notional),
        "clean_rate": summary.get("clean_rate", 0),
        "primary_risk_driver": primary_driver,
        "coverage_gap_count": len(gaps),
        "held_contracts": int(counts.get("review", 0) or 0),
        "monitored_contracts": int(counts.get("monitored", 0) or 0),
        "audit_chain_ok": (infrastructure.get("audit_chain") or {}).get("ok"),
    }

    lenses = {
        "executive": {
            "question": "Where is settlement risk concentrated and does the control system have it contained?",
            "headline": _headline(shared),
            "priorities": [
                _priority("Resolution exposure", f"${exposed_notional/1e6:.1f}M of notional is monitored or held", "high" if held_notional else "medium"),
                _priority("Primary risk driver", f"{primary_driver.title()} is the largest average ambiguity lever across the portfolio", "medium"),
                _priority("Control integrity", "Audit chain verifies" if shared["audit_chain_ok"] is True else "Audit-chain status should be reviewed", "low" if shared["audit_chain_ok"] is True else "high"),
            ],
        },
        "compliance": {
            "question": "Which contracts or controls require intervention before settlement?",
            "headline": f"{len(held)} contract(s) are held for review; {len(monitored)} are under active monitoring.",
            "priorities": [
                *[_priority(r["ticker"], r.get("primary_flag") or "Held for resolution review", "high") for r in top_risks if r.get("verdict", {}).get("key") == "review"],
                *[_priority(g.get("category", "Coverage gap"), g.get("recommendation", "Tighten resolution controls"), "medium") for g in gaps[:3]],
            ][:5],
        },
        "market_ops": {
            "question": "What should we fix in contract design and resolution operations?",
            "headline": f"{primary_driver.title()} is the dominant portfolio weakness; prioritize the highest-risk templates before new listings.",
            "priorities": [
                *[_priority(r["ticker"], r.get("primary_flag") or "Review contract terms", "high" if r.get("verdict", {}).get("key") == "review" else "medium") for r in top_risks[:4]],
                _priority("Template guidance", f"{len(gaps)} category-level coverage gap(s) need stronger drafting guidance", "medium"),
            ],
        },
        "finance": {
            "question": "How much payout/notional is exposed to resolution delay or dispute risk?",
            "headline": f"${held_notional/1e6:.1f}M is held pre-payout and ${monitored_notional/1e6:.1f}M is resolving under monitoring.",
            "priorities": [
                _priority("Held pre-payout", f"${held_notional/1e6:.1f}M requires resolution clearance before funds move", "high" if held_notional else "low"),
                _priority("Monitored exposure", f"${monitored_notional/1e6:.1f}M has identified resolution risk but is not currently blocked", "medium"),
                _priority("Largest exposed contracts", ", ".join(r["ticker"] for r in top_risks[:3]) or "None", "medium"),
            ],
        },
    }

    return {
        "shared": shared,
        "lenses": lenses,
        "top_risks": top_risks,
        "boundary": "Executive intelligence is read-only. Role-specific lenses change presentation and prioritization, never settlement logic.",
    }


def _priority(name: str, detail: str, severity: str) -> dict:
    return {"name": name, "detail": detail, "severity": severity}


def _headline(shared: dict) -> str:
    exposure = shared["resolution_risk_notional"] / 1e6
    held = shared["held_notional"] / 1e6
    if held > 0:
        return f"${exposure:.1f}M of portfolio notional carries identified resolution risk, including ${held:.1f}M currently held before payout."
    return f"${exposure:.1f}M of portfolio notional is monitored; no notional is currently held before payout."
