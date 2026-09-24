"""Arbiter v0.42 auditor workspace: engagements, sampling, testing, findings, sign-off.

An engagement belongs to one auditor: the principal that opened it, together
with an Ed25519 public key whose secret the auditor keeps on their own machine
(tools/arbiter-verify/sign.py). Only that principal can change the engagement,
and sign-off requires the auditor's signature over the report hash, so nobody
who controls Arbiter's database (the exchange included) can produce or alter a
signed report without the auditor's key.

Everything the auditor does is an append-only entry in the engagement's own
hash chain, written in the same transaction as its commitment to Arbiter's main
audit chain. The exchange can see that an audit happened and when.

Sampling is drawn once per engagement, reproducibly: the population is defined
from the audit chain up to a cutoff sequence (see POPULATIONS), the seed is
sha256(engagement_id | chain head hash at the cutoff), and items are ranked by
sha256(seed | item_id). The standalone verifier recomputes the population, the
sample and the period attestation from the evidence package alone.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .resolution_infra import canonical_hash, gen_id, utcnow
from .version import __version__

REPORT_FORMAT = "arbiter.audit-report.v1"
SIGNATURE_PREFIX = "arbiter-audit-report:"
POPULATIONS = {
    "decisions": "Governed decisions recorded in the period (decision.recorded events)",
    "departures": "Departures from precedent in the period (precedent.distinguished / precedent.overruled events)",
    "manual_closes": "Cases closed by a person in the period (work_item.updated to resolved, non-system actor)",
}
RESULTS = ("no_exception", "exception", "not_testable")


def rank(seed: str, item_id: str) -> str:
    return hashlib.sha256(f"{seed}|{item_id}".encode()).hexdigest()


def in_period(ts: str, period_from: str, period_to: str) -> bool:
    """Periods are whole UTC dates, compared on the event timestamp's date part."""
    return period_from <= (ts or "")[:10] <= period_to


def population_from_events(kind: str, events: list[dict[str, Any]], period_from: str, period_to: str) -> list[str]:
    """The sampled population, defined on audit events only. The verifier holds an
    identical copy of this function; keep them the same."""
    out = []
    for e in events:
        if not in_period(e["occurred_at"], period_from, period_to):
            continue
        a, d = e["action"], e.get("details") or {}
        if kind == "decisions" and a == "decision.recorded":
            out.append(e["object_id"])
        elif kind == "departures" and a in ("precedent.distinguished", "precedent.overruled"):
            out.append(e["event_id"])
        elif (
            kind == "manual_closes"
            and a == "work_item.updated"
            and d.get("status") == "resolved"
            and not str(e["actor"]).startswith("system:")
        ):
            out.append(e["event_id"])
    return out


def attestation_from(
    events: list[dict[str, Any]], decisions: dict[str, dict], period_from: str, period_to: str
) -> dict[str, Any]:
    """Period statistics, defined on audit events plus decision records. The
    verifier holds an identical copy; keep them the same."""
    ids = population_from_events("decisions", events, period_from, period_to)
    statuses: dict[str, int] = {}
    for i in ids:
        st = (((decisions.get(i) or {}).get("metadata") or {}).get("precedent_consistency") or {}).get(
            "status"
        ) or "unrecorded"
        statuses[st] = statuses.get(st, 0) + 1
    applied = sum(statuses.get(k, 0) for k in ("follows", "consistent", "divergent"))
    followed = statuses.get("follows", 0) + statuses.get("consistent", 0)
    period = [e for e in events if in_period(e["occurred_at"], period_from, period_to)]
    return {
        "decisions": len(ids),
        "precedent_status": dict(sorted(statuses.items())),
        "followed_when_precedent_applied": round(followed / applied, 3) if applied else None,
        "departures": sum(1 for e in period if e["action"] == "precedent.distinguished"),
        "overrules": sum(1 for e in period if e["action"] == "precedent.overruled"),
        "manual_closes": len(population_from_events("manual_closes", events, period_from, period_to)),
        "deciders": sorted({e["actor"] for e in period if e["action"] == "decision.recorded"}),
    }


class EngagementError(ValueError):
    pass


class Engagements:
    def __init__(self, store):
        self.store = store
        with self.store.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS engagement_log (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    engagement_id TEXT NOT NULL,
                    at TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    previous_hash TEXT,
                    entry_hash TEXT NOT NULL UNIQUE
                );
                CREATE INDEX IF NOT EXISTS ix_engagement_log ON engagement_log(engagement_id, seq);
                CREATE UNIQUE INDEX IF NOT EXISTS ux_engagement_link ON engagement_log(engagement_id, previous_hash);
                """
            )

    # ---- the engagement log ---------------------------------------------

    def _append(self, engagement_id: str, actor: str, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        """One transaction: the entry and its commitment to the main chain land together or not at all."""
        with self.store.connect() as db:
            self.store.lock_audit(db)
            prev = db.execute(
                "SELECT entry_hash FROM engagement_log WHERE engagement_id=? ORDER BY seq DESC LIMIT 1",
                (engagement_id,),
            ).fetchone()
            entry = {
                "engagement_id": engagement_id,
                "at": utcnow(),
                "actor": actor,
                "kind": kind,
                "payload": payload,
                "previous_hash": prev["entry_hash"] if prev else None,
            }
            entry["entry_hash"] = canonical_hash(entry)
            db.execute(
                "INSERT INTO engagement_log(engagement_id,at,actor,kind,payload_json,previous_hash,entry_hash) VALUES(?,?,?,?,?,?,?)",
                (
                    engagement_id,
                    entry["at"],
                    actor,
                    kind,
                    json.dumps(payload, sort_keys=True),
                    entry["previous_hash"],
                    entry["entry_hash"],
                ),
            )
            self.store.append_audit(
                db,
                actor,
                f"audit.engagement.{kind}",
                "audit_engagement",
                engagement_id,
                {"entry_hash": entry["entry_hash"]},
            )
        return entry

    def log(self, engagement_id: str) -> list[dict[str, Any]]:
        with self.store.connect() as db:
            rows = db.execute(
                "SELECT * FROM engagement_log WHERE engagement_id=? ORDER BY seq", (engagement_id,)
            ).fetchall()
        return [
            {
                "engagement_id": r["engagement_id"],
                "at": r["at"],
                "actor": r["actor"],
                "kind": r["kind"],
                "payload": json.loads(r["payload_json"]),
                "previous_hash": r["previous_hash"],
                "entry_hash": r["entry_hash"],
            }
            for r in rows
        ]

    def verify_log(self, engagement_id: str) -> dict[str, Any]:
        prev = None
        entries = self.log(engagement_id)
        for i, e in enumerate(entries):
            body = {k: e[k] for k in ("engagement_id", "at", "actor", "kind", "payload", "previous_hash")}
            if e["previous_hash"] != prev or canonical_hash(body) != e["entry_hash"]:
                return {"ok": False, "entry": i, "reason": "engagement log does not verify"}
            prev = e["entry_hash"]
        return {"ok": True, "entries": len(entries), "head": prev}

    # ---- state (replayed from the log) ------------------------------------

    def get(self, engagement_id: str) -> dict[str, Any] | None:
        entries = self.log(engagement_id)
        if not entries:
            return None
        state: dict[str, Any] = {
            "engagement_id": engagement_id,
            "tests": {},
            "findings": [],
            "sample": None,
            "report": None,
        }
        for e in entries:
            p = e["payload"]
            if e["kind"] == "opened":
                state.update(p, auditor=e["actor"], opened_at=e["at"], state="open")
            elif e["kind"] == "sampled":
                state["sample"] = p
            elif e["kind"] == "tested":
                state["tests"][p["item_id"]] = {**p, "at": e["at"], "by": e["actor"]}
            elif e["kind"] == "finding":
                state["findings"].append({**p, "at": e["at"], "by": e["actor"]})
            elif e["kind"] == "signed":
                state["state"] = "signed"
                state["report"] = p["report"]
                state["signature"] = p["signature"]
                state["signed_at"] = e["at"]
        items = (state["sample"] or {}).get("items") or []
        state["progress"] = {"sampled": len(items), "tested": sum(1 for i in items if i["item_id"] in state["tests"])}
        state["log_head"] = entries[-1]["entry_hash"]
        state["log_entries"] = len(entries)
        return state

    def list(self) -> list[dict[str, Any]]:
        with self.store.connect() as db:
            ids = [
                r["engagement_id"]
                for r in db.execute("SELECT engagement_id FROM engagement_log WHERE kind='opened' ORDER BY seq DESC")
            ]
        out = []
        for i in ids:
            s = self.get(i)
            out.append(
                {
                    k: s.get(k)
                    for k in (
                        "engagement_id",
                        "name",
                        "auditor",
                        "period_from",
                        "period_to",
                        "state",
                        "opened_at",
                        "progress",
                    )
                }
                | {"findings": len(s["findings"])}
            )
        return out

    def _owned_open(self, engagement_id: str, actor: str) -> dict[str, Any]:
        s = self.get(engagement_id)
        if not s:
            raise KeyError(engagement_id)
        if s["auditor"] != actor:
            raise PermissionError("only the engagement's auditor can change it")
        if s["state"] != "open":
            raise EngagementError("the engagement is signed off and locked")
        return s

    # ---- chain reads (one snapshot) -------------------------------------------

    def _chain(self, upto: int | None = None) -> list[dict[str, Any]]:
        sql = "SELECT sequence, event_id, occurred_at, actor, action, object_id, details_json, event_hash FROM audit_events"
        args: tuple = ()
        if upto is not None:
            sql += " WHERE sequence<=?"
            args = (upto,)
        with self.store.connect() as db:
            rows = db.execute(sql + " ORDER BY sequence", args).fetchall()
        return [
            {
                "sequence": r["sequence"],
                "event_id": r["event_id"],
                "occurred_at": r["occurred_at"],
                "actor": r["actor"],
                "action": r["action"],
                "object_id": r["object_id"],
                "details": json.loads(r["details_json"]),
                "event_hash": r["event_hash"],
            }
            for r in rows
        ]

    def _decisions(self) -> dict[str, dict]:
        with self.store.connect() as db:
            return {
                d["decision_id"]: d
                for d in (
                    json.loads(r["decision_json"]) for r in db.execute("SELECT decision_json FROM decision_records")
                )
            }

    # ---- actions ------------------------------------------------------------

    def open(
        self, *, actor: str, name: str, period_from: str, period_to: str, auditor_public_key: str
    ) -> dict[str, Any]:
        if not name.strip():
            raise EngagementError("name is required")
        for d in (period_from, period_to):
            if len(d) != 10 or d[4] != "-" or d[7] != "-":
                raise EngagementError("periods are whole dates, YYYY-MM-DD")
        if period_from > period_to:
            raise EngagementError("period_from must be before period_to")
        try:
            key = bytes.fromhex(auditor_public_key.strip())
        except ValueError as exc:
            raise EngagementError("auditor_public_key must be hex") from exc
        if len(key) != 32:
            raise EngagementError("auditor_public_key must be a 32-byte Ed25519 public key (64 hex characters)")
        eid = gen_id("eng")
        self._append(
            eid,
            actor,
            "opened",
            {"name": name.strip(), "period_from": period_from, "period_to": period_to, "auditor_public_key": key.hex()},
        )
        return self.get(eid)

    def preview(self, engagement_id: str) -> dict[str, Any]:
        s = self.get(engagement_id)
        return attestation_from(self._chain(), self._decisions(), s["period_from"], s["period_to"])

    def sample(self, engagement_id: str, *, actor: str, kind: str, size: int) -> dict[str, Any]:
        s = self._owned_open(engagement_id, actor)
        if s["sample"]:
            raise EngagementError("the sample is drawn once per engagement; open a new engagement to sample again")
        if kind not in POPULATIONS:
            raise EngagementError(f"population must be one of {sorted(POPULATIONS)}")
        if int(size) < 1:
            raise EngagementError("size must be at least 1")
        events = self._chain()
        head = events[-1] if events else None
        pop = population_from_events(kind, events, s["period_from"], s["period_to"])
        seed = hashlib.sha256(f"{engagement_id}|{head['event_hash'] if head else ''}".encode()).hexdigest()
        chosen = sorted(pop, key=lambda i: rank(seed, i))[: min(int(size), len(pop))]
        labels = {e["object_id"] if kind == "decisions" else e["event_id"]: e for e in events}
        decisions = self._decisions() if kind == "decisions" else {}
        items = []
        for i in chosen:
            e = labels.get(i) or {}
            label = (
                (decisions.get(i) or {}).get("selection")
                if kind == "decisions"
                else f"{e.get('action')} {e.get('object_id')}"
            )
            items.append({"item_id": i, "label": label, "at": e.get("occurred_at"), "actor": e.get("actor")})
        self._append(
            engagement_id,
            actor,
            "sampled",
            {
                "population": kind,
                "population_size": len(pop),
                "population_hash": canonical_hash(sorted(pop)),
                "cutoff_sequence": head["sequence"] if head else 0,
                "size": len(chosen),
                "seed": seed,
                "seed_basis": {"engagement_id": engagement_id, "chain_hash": head["event_hash"] if head else None},
                "method": "population from audit events up to cutoff_sequence; rank by sha256(seed|item_id); take the first n",
                "items": items,
            },
        )
        return self.get(engagement_id)

    def checks(self, item_id: str) -> list[dict[str, Any]]:
        """What Arbiter can check mechanically about a sampled item. These assist
        the auditor; the conclusion is the auditor's."""
        out: list[dict[str, Any]] = []
        with self.store.connect() as db:
            row = db.execute("SELECT decision_json FROM decision_records WHERE decision_id=?", (item_id,)).fetchone()
            ev = db.execute("SELECT * FROM audit_events WHERE event_id=?", (item_id,)).fetchone()
            committed = None
            if row:
                d = json.loads(row["decision_json"])
                committed = db.execute(
                    "SELECT 1 FROM audit_events WHERE action='decision.recorded' AND object_id=? AND details_json LIKE ?",
                    (item_id, f"%{d.get('decision_hash')}%"),
                ).fetchone()
        if row:
            out.append(
                {
                    "check": "Decision record hash recomputes",
                    "ok": canonical_hash({k: v for k, v in d.items() if k != "decision_hash"})
                    == d.get("decision_hash"),
                }
            )
            out.append({"check": "Committed to the audit chain", "ok": bool(committed)})
            out.append({"check": "Rationale recorded", "ok": bool((d.get("rationale") or "").strip())})
            pc = (d.get("metadata") or {}).get("precedent_consistency") or {}
            out.append(
                {"check": f"Precedent status recorded ({pc.get('status') or 'none'})", "ok": bool(pc.get("status"))}
            )
            if pc.get("status") == "divergent":
                out.append(
                    {
                        "check": "Departure is distinguished or overrules",
                        "ok": bool(pc.get("distinguish") or pc.get("overrules")),
                    }
                )
            out.append({"check": "Bound to cases", "ok": bool(d.get("affected_case_ids"))})
        elif ev:
            details = json.loads(ev["details_json"])
            out.append({"check": "Event is in the audit chain", "ok": True})
            if ev["action"] == "precedent.distinguished":
                out.append({"check": "Distinction stated", "ok": bool((details.get("distinction") or "").strip())})
            if ev["action"] == "precedent.overruled":
                out.append(
                    {"check": "Overrule reason stated", "ok": bool((details.get("overrule_reason") or "").strip())}
                )
            if ev["action"] == "work_item.updated":
                out.append({"check": "Closing note recorded", "ok": bool((details.get("note") or "").strip())})
        return out

    def test(self, engagement_id: str, *, actor: str, item_id: str, result: str, note: str = "") -> dict[str, Any]:
        s = self._owned_open(engagement_id, actor)
        if item_id not in {i["item_id"] for i in (s["sample"] or {}).get("items") or []}:
            raise EngagementError("item is not in the sample")
        if result not in RESULTS:
            raise EngagementError(f"result must be one of {RESULTS}")
        if result == "exception" and not note.strip():
            raise EngagementError("an exception needs a note")
        self._append(
            engagement_id,
            actor,
            "tested",
            {"item_id": item_id, "result": result, "note": note, "checks": self.checks(item_id)},
        )
        return self.get(engagement_id)

    def finding(
        self, engagement_id: str, *, actor: str, title: str, severity: str, description: str, item_ids: list[str]
    ) -> dict[str, Any]:
        self._owned_open(engagement_id, actor)
        if severity not in ("high", "medium", "low"):
            raise EngagementError("severity must be high, medium or low")
        if not title.strip():
            raise EngagementError("title is required")
        self._append(
            engagement_id,
            actor,
            "finding",
            {
                "finding_id": gen_id("fnd"),
                "title": title,
                "severity": severity,
                "description": description,
                "item_ids": item_ids,
            },
        )
        return self.get(engagement_id)

    def draft(self, engagement_id: str, *, actor: str, opinion: str) -> dict[str, Any]:
        """The report exactly as it will be signed. Deterministic: preparing it
        twice with nothing changed gives the same report_hash."""
        s = self._owned_open(engagement_id, actor)
        items = (s["sample"] or {}).get("items") or []
        if not s["sample"]:
            raise EngagementError("draw the sample before signing")
        untested = [i["item_id"] for i in items if i["item_id"] not in s["tests"]]
        if untested:
            raise EngagementError(f"{len(untested)} sampled items are not tested yet")
        if not opinion.strip():
            raise EngagementError("an opinion is required")
        events = self._chain()
        head = events[-1] if events else None
        results: dict[str, int] = {}
        for t in s["tests"].values():
            results[t["result"]] = results.get(t["result"], 0) + 1
        report = {
            "format": REPORT_FORMAT,
            "engagement_id": engagement_id,
            "name": s["name"],
            "auditor": actor,
            "auditor_public_key": s["auditor_public_key"],
            "period": {"from": s["period_from"], "to": s["period_to"]},
            "product_version": __version__,
            "opinion": opinion.strip(),
            "attestation": attestation_from(events, self._decisions(), s["period_from"], s["period_to"]),
            "sample": {k: v for k, v in s["sample"].items() if k != "items"}
            | {"item_ids": [i["item_id"] for i in items]},
            "results": dict(sorted(results.items())),
            "tests": {k: {"result": v["result"], "note": v["note"]} for k, v in sorted(s["tests"].items())},
            "findings": [
                {k: f[k] for k in ("finding_id", "title", "severity", "description", "item_ids")} for f in s["findings"]
            ],
            "chain": {
                "sequence": head["sequence"] if head else None,
                "event_hash": head["event_hash"] if head else None,
            },
            "engagement_log_head": s["log_head"],
        }
        report["report_hash"] = canonical_hash(report)
        return {"report": report, "sign_message": SIGNATURE_PREFIX + report["report_hash"]}

    def sign(self, engagement_id: str, *, actor: str, opinion: str, report_hash: str, signature: str) -> dict[str, Any]:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

        draft = self.draft(engagement_id, actor=actor, opinion=opinion)["report"]
        if draft["report_hash"] != report_hash:
            raise EngagementError("the record changed since the report was prepared; prepare and sign it again")
        try:
            Ed25519PublicKey.from_public_bytes(bytes.fromhex(draft["auditor_public_key"])).verify(
                bytes.fromhex(signature.strip()), (SIGNATURE_PREFIX + report_hash).encode()
            )
        except (InvalidSignature, ValueError) as exc:
            raise EngagementError("the signature does not verify against the auditor's registered key") from exc
        self._append(engagement_id, actor, "signed", {"report": draft, "signature": signature.strip().lower()})
        return self.get(engagement_id)


_svc: Engagements | None = None


def get_engagements(store) -> Engagements:
    global _svc
    if _svc is None or _svc.store is not store:
        _svc = Engagements(store)
    return _svc
