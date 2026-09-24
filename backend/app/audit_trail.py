"""Arbiter v0.41 audit trail: the governed record, for auditors.

Every action in Arbiter is already written to ``audit_events``, a hash chain in
which each event commits to the one before it. This module turns that chain
into what an auditor needs:

* ``lineage``    everything that happened to one contract, in order, each step
                 tied to its audit event: intake, flags, cases, decisions,
                 precedent, appeals, resolution runs, approvals, settlement.
* ``search``     the whole log, filterable, in plain language.
* ``exceptions`` the events an auditor should look at first: departures from
                 precedent, overrules, reversed decisions, reopened cases, cases
                 closed without a governed decision, self-approval, gaps in
                 anchoring, a broken chain.
* ``anchor``     a receipt of the chain head at a moment in time, for the
                 auditor to keep outside Arbiter. A hash chain proves no single
                 event was edited; a receipt held elsewhere also proves the chain
                 was not regenerated wholesale after the fact.
* ``export``     a self-contained evidence package (arbiter.audit-package.v1,
                 docs/audit/PACKAGE_SPEC.md) that ``tools/arbiter-verify`` checks
                 with the Python standard library alone, on the auditor's own
                 machine.

Reading the record never changes it. Exporting and anchoring are recorded in
the chain, so the auditor's own access is part of the trail.
"""

from __future__ import annotations

import io
import json
import zipfile
from typing import Any, Iterable

from .resolution_infra import canonical_hash, gen_id, utcnow
from .version import __version__

PACKAGE_FORMAT = "arbiter.audit-package.v1"
ANCHOR_FORMAT = "arbiter.audit-anchor.v1"
ANCHOR_STALE_HOURS = 24

# action -> (plain-language label, stage)
ACTIONS: dict[str, tuple[str, str]] = {
    "contract.version.created": ("Contract terms recorded", "intake"),
    "evidence.appended": ("Venue evidence captured", "intake"),
    "evidence.duplicate.ignored": ("Duplicate evidence ignored", "intake"),
    "evidence.exception.opened": ("Flagged for human judgment", "intake"),
    "evidence.exception.reopened": ("Case reopened", "work"),
    "evidence.exception.resolved": ("Case resolved", "work"),
    "evidence.exception.retriaged": ("Case closed by re-triage", "work"),
    "precedent.matched": ("Matched an earlier ruling on arrival", "intake"),
    "work_item.updated": ("Case status changed by an operator", "work"),
    "resolution.reevaluation.requested": ("Re-evaluation requested", "work"),
    "decision.recorded": ("Governed decision recorded", "decision"),
    "decision.reevaluation.requested": ("Cases re-evaluated after the decision", "decision"),
    "precedent.created": ("Decision became precedent", "decision"),
    "precedent.distinguished": ("Precedent distinguished", "decision"),
    "precedent.overruled": ("Precedent overruled", "decision"),
    "precedent.superseded": ("Precedent superseded", "decision"),
    "appeal.checked": ("Appeal checked against the ruling", "appeal"),
    "resolution.run.recorded": ("Resolution run recorded", "resolution"),
    "approval.requested": ("Approval requested", "settlement"),
    "approval.approved": ("Approved", "settlement"),
    "approval.rejected": ("Rejected", "settlement"),
    "settlement.packet.created": ("Signed settlement packet created", "settlement"),
    "audit.anchored": ("Audit chain anchored", "audit"),
    "audit.exported": ("Evidence package exported", "audit"),
    "audit.engagement.opened": ("Audit engagement opened", "audit"),
    "audit.engagement.sampled": ("Audit sample drawn", "audit"),
    "audit.engagement.tested": ("Sample item tested", "audit"),
    "audit.engagement.finding": ("Audit finding recorded", "audit"),
    "audit.engagement.signed": ("Audit engagement signed off", "audit"),
    "policy.draft.created": ("Policy draft created", "governance"),
    "policy.draft.submitted": ("Policy draft submitted", "governance"),
    "policy.draft.approved": ("Policy draft approved", "governance"),
    "policy.version.activated": ("Policy version activated", "governance"),
    "authority.version.created": ("Authority recorded", "governance"),
    "model.invocation.recorded": ("Model invocation recorded", "governance"),
    "model.provider.configured": ("Model provider configured", "governance"),
    "principal.registered": ("Principal registered", "governance"),
}
STAGES = ("intake", "work", "decision", "appeal", "resolution", "settlement", "audit", "governance", "system")


def describe(action: str) -> tuple[str, str]:
    if action in ACTIONS:
        return ACTIONS[action]
    return action.replace(".", " ").replace("_", " ").capitalize(), "system"


def _row(r) -> dict[str, Any]:
    e = {
        "sequence": r["sequence"],
        "event_id": r["event_id"],
        "occurred_at": r["occurred_at"],
        "actor": r["actor"],
        "action": r["action"],
        "object_type": r["object_type"],
        "object_id": r["object_id"],
        "details": json.loads(r["details_json"]),
        "previous_hash": r["previous_hash"],
        "event_hash": r["event_hash"],
    }
    return e


def _values(obj: Any) -> set[str]:
    """Every string value in a details object (nested), for exact id matching."""
    out: set[str] = set()
    if isinstance(obj, str):
        out.add(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            out |= _values(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            out |= _values(v)
    return out


def _humanize(e: dict[str, Any]) -> dict[str, Any]:
    text, stage = describe(e["action"])
    if e["action"] == "work_item.updated" and str(e.get("actor", "")).startswith("system:"):
        text = "Case status set by the system"
    d = e.get("details") or {}
    bits = []
    for key in ("selection", "distinction", "overrule_reason", "reason", "verdict", "status", "note", "tier", "kind"):
        if d.get(key):
            bits.append(f"{key.replace('_', ' ')}: {d[key]}")
    return {**e, "label": text, "stage": stage, "summary": "; ".join(str(b) for b in bits)[:240]}


class AuditTrail:
    def __init__(self, store):
        self.store = store
        self._chain_cache: tuple[tuple, dict] | None = None

    def chain(self) -> dict[str, Any]:
        """verify_audit_chain, cached until the chain grows (it is append-only)."""
        with self.store.connect() as db:
            row = db.execute("SELECT COUNT(*) n, MAX(sequence) s FROM audit_events").fetchone()
        key = (row["n"], row["s"])
        if self._chain_cache and self._chain_cache[0] == key:
            return self._chain_cache[1]
        result = self.store.verify_audit_chain()
        self._chain_cache = (key, result)
        return result

    def _all_decisions(self) -> list[dict[str, Any]]:
        with self.store.connect() as db:
            return [
                json.loads(r["decision_json"])
                for r in db.execute("SELECT decision_json FROM decision_records ORDER BY created_at")
            ]

    # ---- reading --------------------------------------------------------

    def _events(self, where: str = "", args: Iterable[Any] = (), order: str = "ASC", limit: int | None = None):
        sql = f"SELECT * FROM audit_events {where} ORDER BY sequence {order}"
        if limit:
            sql += f" LIMIT {int(limit)}"
        with self.store.connect() as db:
            return [_row(r) for r in db.execute(sql, tuple(args)).fetchall()]

    def search(
        self,
        *,
        q: str = "",
        actor: str = "",
        action: str = "",
        stage: str = "",
        object_id: str = "",
        since: str = "",
        until: str = "",
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        clauses, args = [], []
        if actor:
            clauses.append("actor=?")
            args.append(actor)
        if action:
            clauses.append("action=?")
            args.append(action)
        if object_id:
            clauses.append("(object_id=? OR details_json LIKE ?)")
            args += [object_id, f"%{object_id}%"]
        if since:
            clauses.append("occurred_at>=?")
            args.append(since)
        if until:
            clauses.append("occurred_at<=?")
            args.append(until)
        if q:
            clauses.append("(action LIKE ? OR actor LIKE ? OR object_id LIKE ? OR details_json LIKE ?)")
            args += [f"%{q}%"] * 4
        if stage:
            actions = [a for a, (_, s) in ACTIONS.items() if s == stage]
            if not actions:
                return {"events": [], "total": 0, "facets": self.facets()}
            clauses.append(f"action IN ({','.join('?' for _ in actions)})")
            args += actions
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.store.connect() as db:
            total = db.execute(f"SELECT COUNT(*) n FROM audit_events {where}", tuple(args)).fetchone()["n"]
            rows = db.execute(
                f"SELECT * FROM audit_events {where} ORDER BY sequence DESC LIMIT ? OFFSET ?",
                (*args, max(1, min(int(limit), 500)), max(0, int(offset))),
            ).fetchall()
        return {"events": [_humanize(_row(r)) for r in rows], "total": total, "facets": self.facets()}

    def facets(self) -> dict[str, Any]:
        with self.store.connect() as db:
            actions = {
                r["action"]: r["n"] for r in db.execute("SELECT action, COUNT(*) n FROM audit_events GROUP BY action")
            }
            actors = {
                r["actor"]: r["n"] for r in db.execute("SELECT actor, COUNT(*) n FROM audit_events GROUP BY actor")
            }
        stages: dict[str, int] = {}
        for a, n in actions.items():
            stages[describe(a)[1]] = stages.get(describe(a)[1], 0) + n
        return {"actions": actions, "actors": actors, "stages": stages}

    # ---- lineage ----------------------------------------------------------

    def lineage(self, contract_id: str) -> dict[str, Any]:
        """Everything that happened to one contract, each step tied to its audit event."""
        from .active_evidence import get_service as get_evidence
        from .decision_records import get_service as get_decisions

        spec = self.store.latest_contract(contract_id)
        if not spec:
            raise KeyError(contract_id)
        with self.store.connect() as db:
            versions = [
                {
                    "version": r["version"],
                    "created_at": r["created_at"],
                    "created_by": r["created_by"],
                    "spec_hash": r["spec_hash"],
                }
                for r in db.execute(
                    "SELECT version, created_at, created_by, spec_hash FROM contract_versions WHERE contract_id=? ORDER BY version",
                    (contract_id,),
                )
            ]
            runs = [
                r["run_id"]
                for r in db.execute("SELECT run_id FROM resolution_runs WHERE contract_id=?", (contract_id,))
            ]
            try:
                approvals = [
                    r["approval_id"]
                    for r in db.execute(
                        f"SELECT approval_id FROM approval_requests WHERE object_id IN ({','.join('?' for _ in [contract_id, *runs])})",
                        (contract_id, *runs),
                    )
                ]
            except Exception:  # approvals table absent on a fresh database
                approvals = []
        exceptions = [
            e
            for e in get_evidence(self.store).list_exceptions(active_only=False)
            if e.get("contract_id") == contract_id
        ]
        work_ids = {e["work_item_id"] for e in exceptions}
        decisions = [d for d in self._all_decisions() if work_ids & set(d.get("affected_case_ids") or [])]
        decision_ids = {d["decision_id"] for d in decisions}

        keys = {contract_id, *runs, *approvals, *work_ids, *decision_ids}
        keys |= {e["exception_id"] for e in exceptions}
        keys |= {e["subject"] for e in exceptions}
        events = []
        keys = {k for k in keys if k}
        likes = " OR ".join("details_json LIKE ?" for _ in keys)
        candidates = self._events(
            f"WHERE object_id IN ({','.join('?' for _ in keys)}) OR {likes}",
            [*keys, *[f"%{k}%" for k in keys]],
        )
        for e in candidates:
            if e["object_type"] == "contract" and e["object_id"] != contract_id:
                continue  # another contract's event (e.g. it matched this contract's ruling)
            if e["object_type"] in ("work_item", "evidence_exception") and e["object_id"] not in keys:
                continue  # a sibling case touched by the same decision
            if e["object_id"] in keys:
                events.append(e)
                continue
            if keys & _values(e["details"]):
                events.append(e)
        events = [_humanize(e) for e in events]
        by_decision = {d["decision_id"]: d for d in decisions}
        for e in events:
            if e["action"] == "decision.recorded" and e["object_id"] in by_decision:
                d = by_decision[e["object_id"]]
                e["summary"] = f"ruling: {d.get('selection')}; by {d.get('actor')}"

        governing = None
        if decisions:
            d = max(decisions, key=lambda x: x.get("created_at") or "")
            live = not get_decisions(self.store).is_superseded(d["decision_id"])
            governing = {
                "decision_id": d["decision_id"],
                "selection": d.get("selection"),
                "rationale": d.get("rationale"),
                "governing_rule": d.get("governing_rule"),
                "actor": d.get("actor"),
                "created_at": d.get("created_at"),
                "decision_hash": d.get("decision_hash"),
                "precedent_consistency": (d.get("metadata") or {}).get("precedent_consistency"),
                "authoritative": live,
            }
        chain = self.chain()
        meta = spec.get("metadata") or {}
        return {
            "contract": {
                "contract_id": contract_id,
                "title": spec.get("title"),
                "venue": meta.get("venue"),
                "source_url": meta.get("source_url"),
                "event_id": meta.get("event_id"),
                "rules": (spec.get("definition") or {}).get("yes_if"),
                "versions": versions,
            },
            "cases": [
                {
                    "work_item_id": e["work_item_id"],
                    "kind": e["kind"],
                    "status": e["status"],
                    "title": e.get("title"),
                    "detail": e.get("detail"),
                }
                for e in exceptions
            ],
            "governing_decision": governing,
            "decisions": [d["decision_id"] for d in decisions],
            "runs": runs,
            "approvals": approvals,
            "events": events,
            "stages": [s for s in STAGES if any(e["stage"] == s for e in events)],
            "lineage_hash": canonical_hash([e["event_hash"] for e in events]),
            "chain": chain,
        }

    # ---- exceptions ---------------------------------------------------------

    def exceptions(self) -> dict[str, Any]:
        """Events an auditor should look at first, each with the evidence."""
        items: list[dict[str, Any]] = []

        def add(kind, severity, title, detail, event=None, **extra):
            items.append(
                {
                    "kind": kind,
                    "severity": severity,
                    "title": title,
                    "detail": detail,
                    "sequence": (event or {}).get("sequence"),
                    "occurred_at": (event or {}).get("occurred_at"),
                    "actor": (event or {}).get("actor"),
                    "event_hash": (event or {}).get("event_hash"),
                    **extra,
                }
            )

        chain = self.chain()
        if not chain.get("ok"):
            add(
                "chain_broken",
                "critical",
                "The audit chain does not verify",
                f"{chain.get('reason')} at sequence {chain.get('sequence')}",
            )

        events = self._events()
        opened_by_actor: dict[str, set[str]] = {}
        decided_cases = {
            str(c)
            for e in events
            if e["action"] == "decision.recorded"
            for c in (e["details"] or {}).get("affected_case_ids") or []
        }
        for e in events:
            d = e["details"] or {}
            a = e["action"]
            if a == "precedent.distinguished":
                add(
                    "departure",
                    "high",
                    f"Departed from precedent {e['object_id']}",
                    d.get("distinction") or "",
                    e,
                    precedent_id=e["object_id"],
                    decision_id=d.get("by_decision"),
                )
            elif a == "precedent.overruled":
                add(
                    "overrule",
                    "high",
                    f"Precedent {e['object_id']} overruled by {d.get('overruled_by')}",
                    d.get("overrule_reason") or "",
                    e,
                    precedent_id=e["object_id"],
                    decision_id=d.get("overruled_by"),
                )
            elif a == "precedent.superseded":
                add(
                    "reversal",
                    "medium",
                    f"Decision {e['object_id']} was superseded",
                    d.get("reason") or "",
                    e,
                    decision_id=e["object_id"],
                )
            elif a == "evidence.exception.reopened":
                add(
                    "reopened",
                    "medium",
                    f"Case reopened: {d.get('subject') or e['object_id']}",
                    d.get("reason") or "",
                    e,
                )
            elif a == "evidence.exception.retriaged":
                add(
                    "auto_closed",
                    "low",
                    f"Case closed by re-triage, not by a person: {d.get('subject')}",
                    f"now: {d.get('now') or 'no human judgment needed'}",
                    e,
                )
            elif (
                a == "work_item.updated"
                and str(d.get("status")) == "resolved"
                and not str(e["actor"]).startswith("system:")
                and e["object_id"] not in decided_cases
            ):
                add(
                    "manual_close",
                    "medium",
                    f"Case closed by hand without a governed decision: {e['object_id']}",
                    d.get("note") or "",
                    e,
                )
            elif a == "approval.requested":
                opened_by_actor.setdefault(d.get("approval_id"), set()).add(e["actor"])
            elif a == "approval.approved":
                requesters = opened_by_actor.get(d.get("approval_id")) or set()
                if e["actor"] in requesters:
                    add(
                        "self_approval",
                        "high",
                        f"Same person requested and approved {d.get('approval_id')}",
                        e["actor"],
                        e,
                    )

        # Decider approving settlement of the same contract.

        with self.store.connect() as db:
            try:
                rows = db.execute(
                    "SELECT r.contract_id, d.actor FROM approval_decisions d JOIN approval_requests q ON q.approval_id=d.approval_id "
                    "JOIN resolution_runs r ON r.run_id=q.object_id WHERE d.decision='approve'"
                ).fetchall()
            except Exception:
                rows = []
        if rows:
            ex = {}
            from .active_evidence import get_service as get_evidence

            for e in get_evidence(self.store).list_exceptions(active_only=False):
                if e.get("contract_id"):
                    ex.setdefault(e["work_item_id"], e["contract_id"])
            deciders: dict[str, set[str]] = {}
            for d in self._all_decisions():
                for w in d.get("affected_case_ids") or []:
                    if w in ex:
                        deciders.setdefault(ex[w], set()).add(d.get("actor"))
            for r in rows:
                if r["actor"] in deciders.get(r["contract_id"], set()):
                    add(
                        "decided_and_approved",
                        "high",
                        f"Same person decided and approved settlement of {r['contract_id']}",
                        r["actor"],
                    )

        anchors = self.anchors()
        last = anchors[0]["anchored_at"] if anchors else None
        if events and not anchors:
            add(
                "unanchored",
                "medium",
                "The chain has never been anchored",
                "No receipt of the chain head exists outside Arbiter yet.",
            )
        elif last:
            from datetime import datetime, timezone

            age = (
                datetime.now(timezone.utc) - datetime.fromisoformat(last.replace("Z", "+00:00"))
            ).total_seconds() / 3600
            behind = (events[-1]["sequence"] - anchors[0]["sequence"]) if events else 0
            if age > ANCHOR_STALE_HOURS and behind > 0:
                add("stale_anchor", "low", f"Last anchor is {int(age)}h old", f"{behind} events since the last anchor.")

        order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        items.sort(key=lambda i: (order.get(i["severity"], 9), -(i["sequence"] or 0)))
        counts: dict[str, int] = {}
        for i in items:
            counts[i["kind"]] = counts.get(i["kind"], 0) + 1
        return {"items": items, "counts": counts, "chain": chain}

    # ---- anchoring -------------------------------------------------------------

    def anchor(self, *, actor: str, note: str = "") -> dict[str, Any]:
        """Record a receipt of the current chain head. Give the receipt to someone
        outside Arbiter (the auditor): it later proves the chain up to that point
        was not rewritten. The receipt is stored in the chain itself, in one write."""
        with self.store.connect() as db:
            head = db.execute("SELECT sequence, event_hash FROM audit_events ORDER BY sequence DESC LIMIT 1").fetchone()
        if not head:
            raise ValueError("nothing to anchor: the audit chain is empty")
        receipt = {
            "format": ANCHOR_FORMAT,
            "anchor_id": gen_id("anc"),
            "sequence": head["sequence"],
            "event_hash": head["event_hash"],
            "anchored_at": utcnow(),
            "anchored_by": actor,
            "product_version": __version__,
            "note": note,
        }
        receipt["receipt_hash"] = canonical_hash(receipt)
        self.store._audit(actor, "audit.anchored", "audit_anchor", receipt["anchor_id"], {"receipt": receipt})
        return receipt

    def anchors(self) -> list[dict[str, Any]]:
        return [
            e["details"]["receipt"]
            for e in self._events("WHERE action='audit.anchored'", order="DESC")
            if isinstance((e["details"] or {}).get("receipt"), dict)
        ]

    # ---- export ------------------------------------------------------------------

    def package(self, *, actor: str) -> tuple[bytes, dict[str, Any]]:
        """The whole governed record as a zip the auditor verifies independently."""
        with self.store.connect() as db:
            # One read transaction: events and records come from the same snapshot,
            # so nothing written mid-export appears in one without the other.
            # Known limit: on Postgres this runs at the connection's default isolation
            # (READ COMMITTED), so a write landing mid-export can still split; export
            # there from a quiesced replica until REPEATABLE READ is wired in.
            if self.store.backend == "sqlite":
                db.execute("BEGIN")
            events = [_row(r) for r in db.execute("SELECT * FROM audit_events ORDER BY sequence").fetchall()]
            decisions = [
                json.loads(r["decision_json"])
                for r in db.execute("SELECT decision_json FROM decision_records ORDER BY created_at")
            ]
            contracts = [
                json.loads(r["spec_json"])
                for r in db.execute("SELECT spec_json FROM contract_versions ORDER BY contract_id, version")
            ]
            evidence = [
                json.loads(r["record_json"])
                for r in db.execute("SELECT record_json FROM evidence_records ORDER BY retrieved_at")
            ]
            try:
                precedents = [
                    json.loads(r["precedent_json"])
                    for r in db.execute("SELECT precedent_json FROM precedents ORDER BY created_at")
                ]
            except Exception:
                precedents = []
            try:
                engagement_log = [
                    {
                        "engagement_id": r["engagement_id"],
                        "at": r["at"],
                        "actor": r["actor"],
                        "kind": r["kind"],
                        "payload": json.loads(r["payload_json"]),
                        "previous_hash": r["previous_hash"],
                        "entry_hash": r["entry_hash"],
                    }
                    for r in db.execute("SELECT * FROM engagement_log ORDER BY seq")
                ]
            except Exception:
                engagement_log = []
        files = {
            "events.jsonl": events,
            "decisions.jsonl": decisions,
            "contracts.jsonl": contracts,
            "evidence.jsonl": evidence,
            "precedents.jsonl": precedents,
            "anchors.jsonl": [
                e["details"]["receipt"]
                for e in events
                if e["action"] == "audit.anchored" and isinstance(e["details"].get("receipt"), dict)
            ],
            "engagements.jsonl": engagement_log,
        }
        blobs = {
            name: "".join(json.dumps(r, sort_keys=True, default=str) + "\n" for r in rows).encode()
            for name, rows in files.items()
        }
        import hashlib

        manifest = {
            "format": PACKAGE_FORMAT,
            "generated_at": utcnow(),
            "generated_by": actor,
            "product_version": __version__,
            "range": {
                "from_sequence": events[0]["sequence"] if events else None,
                "to_sequence": events[-1]["sequence"] if events else None,
                "from_time": events[0]["occurred_at"] if events else None,
                "to_time": events[-1]["occurred_at"] if events else None,
            },
            "chain": {
                "first_previous_hash": events[0]["previous_hash"] if events else None,
                "head_hash": events[-1]["event_hash"] if events else None,
            },
            "counts": {name.split(".")[0]: len(rows) for name, rows in files.items()},
            "files": {name: "sha256:" + hashlib.sha256(b).hexdigest() for name, b in blobs.items()},
            "spec": "docs/audit/PACKAGE_SPEC.md",
            "verify": "python3 verify.py <this package>",
        }
        manifest["manifest_hash"] = canonical_hash(manifest)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("manifest.json", json.dumps(manifest, indent=2, sort_keys=True))
            for name, b in blobs.items():
                z.writestr(name, b)
            z.writestr(
                "README.txt",
                "Arbiter audit evidence package ("
                + PACKAGE_FORMAT
                + ").\n\nVerify it on your own machine with the standalone verifier, which needs only Python 3.9+:\n\n"
                "    python3 verify.py arbiter-audit-package.zip --anchor your-receipt.json\n\n"
                "The verifier and the format spec are published with Arbiter (tools/arbiter-verify, docs/audit/PACKAGE_SPEC.md).\n"
                "Use your own copy of the verifier, not one supplied inside a package.\n",
            )
        data = buf.getvalue()
        self.store._audit(
            actor,
            "audit.exported",
            "audit_package",
            manifest["manifest_hash"],
            {
                "head_hash": manifest["chain"]["head_hash"],
                "to_sequence": manifest["range"]["to_sequence"],
                "counts": manifest["counts"],
            },
        )
        return data, manifest

    def overview(self) -> dict[str, Any]:
        chain = self.chain()
        anchors = self.anchors()
        exc = self.exceptions()
        with self.store.connect() as db:
            head = db.execute(
                "SELECT sequence, occurred_at FROM audit_events ORDER BY sequence DESC LIMIT 1"
            ).fetchone()
            first = db.execute("SELECT occurred_at FROM audit_events ORDER BY sequence ASC LIMIT 1").fetchone()
            decisions = db.execute("SELECT COUNT(*) n FROM decision_records").fetchone()["n"]
            actors = db.execute("SELECT COUNT(DISTINCT actor) n FROM audit_events").fetchone()["n"]
        return {
            "chain": chain,
            "events": chain.get("events", 0),
            "first_event_at": first["occurred_at"] if first else None,
            "head_sequence": head["sequence"] if head else None,
            "head_at": head["occurred_at"] if head else None,
            "decisions": decisions,
            "actors": actors,
            "anchors": anchors[:10],
            "events_since_anchor": (head["sequence"] - anchors[0]["sequence"])
            if (head and anchors)
            else (head["sequence"] if head else 0),
            "exception_counts": exc["counts"],
            "exceptions_total": len(exc["items"]),
            "format": PACKAGE_FORMAT,
        }


_trail: AuditTrail | None = None


def get_trail(store) -> AuditTrail:
    global _trail
    if _trail is None or _trail.store is not store:
        _trail = AuditTrail(store)
    return _trail
