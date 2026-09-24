"""Arbiter v0.39 precedent engine.

Every governed decision becomes a precedent: the ruling (selection, governing
rule, rationale), the contracts it decided, and the clauses in those contracts
that needed the judgment. When a new contract arrives, Arbiter checks it
against every live precedent and says, with the evidence, whether an earlier
ruling applies:

* ``same_clause``   the clause that was ruled on appears in this contract
                     (near-verbatim, names and numbers aside). The ruling applies.
* ``same_template`` the contract is the same template as a decided one
                     (e.g. the next event of the same series). The ruling likely applies.
* ``related``       similar wording; shown for context only.

Matching is deterministic and explainable: TF-IDF cosine over contract text
and title shape, and token cosine over normalized clauses. No model is involved
and no score is hidden. Thresholds were set on 838 real Kalshi/Polymarket markets
(see scripts/precedent_eval.py and docs/benchmark/PRECEDENT_MATCHING.md).

Precedents never decide anything. A matching precedent is surfaced to the
operator, and departing from an applicable precedent requires either a stated
distinction or an explicit overrule. Both are recorded in the audit chain.
Overruling is prospective: the overruled decision stays authoritative for the
cases it decided and stops guiding new ones.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from typing import Any, Iterable

from .real_benchmark.hardness import DISCLAIMER_MARKERS, INTERPRETIVE_TERMS, VAGUE_SOURCE_MARKERS, VOID_MARKERS
from .resolution_infra import canonical_hash, utcnow

VERSION = "0.39.0"
ACTOR = "system:precedent-engine"

# Tier thresholds, chosen on the Sep 23/24 2026 live scans (838 markets):
# contract similarity >= 0.80 recovered the same template in another event for
# 80% of markets with no wrong top match; every non-family pair above 0.80 was
# the same template under another ticker. Clause similarity >= 0.85 is
# near-verbatim (names/numbers already normalized out).
SAME_CLAUSE = 0.85
SAME_TEMPLATE = 0.80
RELATED = 0.60
TIERS = ("same_clause", "same_template", "related")
APPLICABLE = frozenset({"same_clause", "same_template"})
CLAUSE_PREFILTER = 0.25  # share of a clause's word pairs a sentence must share to be scored
SELECTION_AGREES = 0.5  # token Jaccard between two rulings' selections

# Which wording in a contract a ruling of each review class is about.
CLASS_MARKERS: dict[str, tuple[str, ...]] = {
    "interpretive_criteria": tuple(INTERPRETIVE_TERMS) + tuple(VAGUE_SOURCE_MARKERS),
    "disputed": tuple(DISCLAIMER_MARKERS),
    "multi_source_conflict": tuple(VAGUE_SOURCE_MARKERS)
    + ("official", "certified", "certif", "ambiguity", "electoral authority"),
    "revised_source": ("revis", "initial", "preliminary", "first release", "as reported", "release"),
    "late_or_void": tuple(VOID_MARKERS) + ("postpone", "cancel", "delay", "void"),
}
ALL_MARKERS = tuple(sorted({m for ms in CLASS_MARKERS.values() for m in ms}))

KIND_TO_CLASS = {
    "policy_review": "interpretive_criteria",
    "authority_conflict": "multi_source_conflict",
    "timing_revision": "revised_source",
    "operator_review": "late_or_void",
}

_STOP = frozenset(
    "the a an of to in on for by at is be will this that if and or as with any from are was were it its "
    "than then market resolves yes no".split()
)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")


# --------------------------------------------------------------------------
# text features
# --------------------------------------------------------------------------


def normalize_clause(sentence: str) -> str:
    """Names and numbers out, so the same clause compares equal across events.
    Same normalization venue intake uses for template detection."""
    s = re.sub(
        r"\b[A-Z][\w'&.-]*(?:\s+(?:(?:of|the|and|for|de|la|du|von|der|van|den)\s+)*[A-Z][\w'&.-]*)*", "<x>", sentence
    )
    s = re.sub(r"\d+(?:\.\d+)?", "<n>", s)
    return re.sub(r"\s+", " ", s).strip().lower()


def sentences(rules: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_SPLIT.split(str(rules or "")) if len(s.strip()) > 12]


def issue_clauses(row: dict[str, Any], review_class: str | None) -> list[dict[str, str]]:
    """The sentences of a contract a ruling of ``review_class`` is about."""
    markers = CLASS_MARKERS.get(review_class or "", ALL_MARKERS)
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for s in sentences(row.get("rules") or ""):
        low = s.lower()
        if any(m in low for m in markers):
            norm = normalize_clause(s)
            if norm not in seen:
                seen.add(norm)
                out.append({"text": s, "normalized": norm})
    return out


def _words(text: str) -> list[str]:
    text = re.sub(r"\d+(?:\.\d+)?", " NUM ", text)
    return [t for t in re.findall(r"[a-z]+|NUM", text.lower()) if t not in _STOP]


def _grams(words: list[str]) -> list[str]:
    return words + [a + "_" + b for a, b in zip(words, words[1:])]


def contract_terms(title: str, rules: str) -> Counter:
    # The title is counted twice: it states the question; rules are mostly mechanics.
    return Counter(_grams(_words(f"{title} {title} {rules}")))


def shape_terms(title: str) -> Counter:
    w = normalize_clause(title).split()
    return Counter(w + [a + "_" + b for a, b in zip(w, w[1:])])


def clause_terms(normalized: str) -> Counter:
    w = re.findall(r"<x>|<n>|[a-z]+", normalized)
    return Counter(w + [a + "_" + b for a, b in zip(w, w[1:])])


def _idf(docs: Iterable[Counter]) -> dict[str, float]:
    df: Counter = Counter()
    n = 0
    for d in docs:
        n += 1
        df.update(d.keys())
    return {t: math.log((n + 1) / (c + 1)) + 1 for t, c in df.items()}


def _unit(counts: Counter, idf: dict[str, float] | None = None) -> dict[str, float]:
    v = {t: (1 + math.log(c)) * ((idf or {}).get(t, 1.0) if idf is not None else 1.0) for t, c in counts.items() if c}
    norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
    return {t: x / norm for t, x in v.items()}


def cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(x * b.get(t, 0.0) for t, x in a.items())


def agrees(a: str, b: str) -> bool:
    """Two rulings' selections say the same thing (word overlap, or verbatim)."""
    return a.strip().lower() == b.strip().lower() or jaccard(a, b) >= SELECTION_AGREES


def jaccard(a: str, b: str) -> float:
    sa, sb = set(_words(a)), set(_words(b))
    return len(sa & sb) / len(sa | sb) if sa and sb else 0.0


def series_of(row: dict[str, Any]) -> str:
    """Kalshi series ticker (event ticker prefix); Polymarket has no series, use the event."""
    event = str(row.get("event_id") or row.get("market_id") or "")
    return event.split("-")[0] if row.get("venue") == "kalshi" else f"{row.get('venue')}:{event}"


# Ask Arbiter vocabulary. Questions are phrased the way people talk ("dies",
# "steps down"); contracts are phrased the way rules are written ("death",
# "leave office"). A small, declared lexicon bridges the common resolution
# terms. It is data, not a model, and every hit is shown in the citation.
ASK_LEXICON = {
    "die": "death",
    "dies": "death",
    "died": "death",
    "dying": "death",
    "dead": "death",
    "deceased": "death",
    "resign": "resign",
    "resigns": "resign",
    "resigned": "resign",
    "resignation": "resign",
    "leave": "leave",
    "leaves": "leave",
    "leaving": "leave",
    "left": "leave",
    "departure": "leave",
    "depart": "leave",
    "departs": "leave",
    "vacate": "leave",
    "vacated": "leave",
    "vacancy": "leave",
    "interim": "interim",
    "acting": "interim",
    "caretaker": "interim",
    "revised": "revision",
    "revise": "revision",
    "revisions": "revision",
    "revision": "revision",
    "official": "official",
    "officially": "official",
    "certified": "certify",
    "certification": "certify",
    "certify": "certify",
    "postponed": "postpone",
    "postponement": "postpone",
    "cancelled": "cancel",
    "canceled": "cancel",
    "cancellation": "cancel",
    "voided": "void",
    "tie": "tie",
    "tied": "tie",
}
ASK_STOP = _STOP | frozenset(
    "what how do does did we us our should would could can when which who whom whose why happens happen "
    "about there here into under over case cases rule ruled ruling arbiter".split()
)
ASK_COVERAGE = 0.34


def _stem(word: str) -> str:
    if word in ASK_LEXICON:
        return ASK_LEXICON[word]
    for suffix in ("ations", "ation", "ings", "ing", "ies", "ied", "ed", "es", "s", "ly"):
        if len(word) > len(suffix) + 3 and word.endswith(suffix):
            word = word[: -len(suffix)]
            break
    return ASK_LEXICON.get(word, word)


def ask_terms(text: str) -> list[str]:
    return [_stem(w) for w in re.findall(r"[a-z0-9]+", str(text).lower()) if w not in ASK_STOP and len(w) > 1]


def _precedent_text(p: dict[str, Any]) -> str:
    return " ".join(
        [p.get("question") or "", p.get("selection") or "", p.get("rationale") or "", p.get("governing_rule") or ""]
        + [f"{c.get('title') or ''} {c.get('label') or ''}" for c in p.get("contracts") or []]
        + [c["text"] for c in p.get("clauses") or []]
    )


class Corpus:
    """IDF over a reference set of contracts, so similarity reflects what is
    distinctive in THIS venue universe (templated words weigh little)."""

    def __init__(self, rows: Iterable[dict[str, Any]]):
        rows = list(rows)
        self.text_idf = _idf(contract_terms(r.get("title") or "", r.get("rules") or "") for r in rows)
        self.shape_idf = _idf(shape_terms(r.get("title") or "") for r in rows)
        self.size = len(rows)
        self._cache: dict[tuple, tuple] = {}
        self._clauses: dict[str, dict[str, float]] = {}

    def vectors(self, row: dict[str, Any]) -> tuple[dict[str, float], dict[str, float]]:
        # Keyed by the text itself, not the contract id: a precedent's snapshot
        # of a contract and that contract's current version must never share
        # a vector once the rules change.
        key = (row.get("title") or "", row.get("rules") or "")
        if key in self._cache:
            return self._cache[key]
        vec = (
            _unit(contract_terms(row.get("title") or "", row.get("rules") or ""), self.text_idf),
            _unit(shape_terms(row.get("title") or ""), self.shape_idf),
        )
        self._cache[key] = vec
        return vec

    def clause_vector(self, normalized: str) -> dict[str, float]:
        vec = self._clauses.get(normalized)
        if vec is None:
            vec = self._clauses[normalized] = _unit(clause_terms(normalized))
        return vec

    def similarity(self, a: tuple, b: tuple) -> float:
        return 0.7 * cosine(a[0], b[0]) + 0.3 * cosine(a[1], b[1])


# --------------------------------------------------------------------------
# the engine
# --------------------------------------------------------------------------


class PrecedentEngine:
    def __init__(self, store):
        self.store = store
        self._corpus: Corpus | None = None
        self._corpus_key: tuple | None = None
        self._init_db()

    def _init_db(self) -> None:
        with self.store.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS precedents (
                    precedent_id TEXT PRIMARY KEY,
                    decision_type TEXT NOT NULL,
                    review_class TEXT,
                    state TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    precedent_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS precedent_matches (
                    contract_id TEXT NOT NULL,
                    precedent_id TEXT NOT NULL,
                    tier TEXT NOT NULL,
                    score REAL NOT NULL,
                    matched_at TEXT NOT NULL,
                    match_json TEXT NOT NULL,
                    PRIMARY KEY (contract_id, precedent_id)
                );
                CREATE INDEX IF NOT EXISTS ix_precedent_matches_precedent
                    ON precedent_matches(precedent_id, tier);
                """
            )

    # ---- building precedents from decisions ------------------------------

    def _exceptions_by_work_item(self) -> dict[str, dict[str, Any]]:
        from .active_evidence import get_service as get_evidence_service

        return {e["work_item_id"]: e for e in get_evidence_service(self.store).list_exceptions(active_only=False)}

    def _contract_row(self, contract_id: str) -> dict[str, Any] | None:
        from .venue_intake import _row_from_store

        row = _row_from_store(self.store, contract_id)
        if row:
            row["contract_id"] = contract_id
        return row

    @staticmethod
    def _review_class(exception: dict[str, Any]) -> str | None:
        meta = exception.get("metadata") or {}
        if meta.get("review_class"):
            return meta["review_class"]
        m = re.search(r"Needs a human judgment \(([a-z ]+)\)", str(exception.get("detail") or ""))
        if m:
            return m.group(1).replace(" ", "_")
        return KIND_TO_CLASS.get(str(exception.get("kind") or ""))

    def build(self, decision: dict[str, Any], exceptions: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
        """Create or refresh the precedent for one decision record."""
        exceptions = self._exceptions_by_work_item() if exceptions is None else exceptions
        contracts: list[dict[str, Any]] = []
        clauses: list[dict[str, str]] = []
        classes: Counter = Counter()
        for case_id in decision.get("affected_case_ids") or []:
            exc = exceptions.get(case_id)
            if not exc or not exc.get("contract_id"):
                continue
            row = self._contract_row(exc["contract_id"])
            if not row:
                continue
            klass = self._review_class(exc)
            if klass:
                classes[klass] += 1
            contracts.append(
                {
                    "contract_id": row["contract_id"],
                    "venue": row["venue"],
                    "market_id": row["market_id"],
                    "event_id": row.get("event_id"),
                    "series": series_of(row),
                    "title": row.get("title") or "",
                    "rules": row.get("rules") or "",
                    "label": str(exc.get("recommended_action") or exc.get("action") or "").split(": ", 1)[-1],
                }
            )
            for c in issue_clauses(row, klass):
                if c["normalized"] not in {x["normalized"] for x in clauses}:
                    clauses.append(c)
        review_class = classes.most_common(1)[0][0] if classes else None
        now = utcnow()
        precedent = {
            "schema": "arbiter.precedent.v1",
            "precedent_id": decision["decision_id"],
            "decision_id": decision["decision_id"],
            "decision_hash": decision.get("decision_hash"),
            "decision_type": decision.get("decision_type"),
            "review_class": review_class,
            "question": decision.get("question") or "",
            "selection": decision.get("selection") or "",
            "rationale": decision.get("rationale") or "",
            "governing_rule": decision.get("governing_rule") or "",
            "cluster_id": decision.get("cluster_id"),
            "decided_by": decision.get("actor"),
            "decided_at": decision.get("created_at"),
            "contracts": contracts,
            "clauses": clauses,
            "state": "active",
        }
        existing = self.get(decision["decision_id"])
        if existing and existing.get("state") == "overruled":
            precedent["state"] = "overruled"
            precedent["overruled_by"] = existing.get("overruled_by")
        with self.store.connect() as db:
            db.execute(
                "INSERT INTO precedents(precedent_id,decision_type,review_class,state,created_at,updated_at,precedent_json) "
                "VALUES(?,?,?,?,?,?,?) ON CONFLICT(precedent_id) DO UPDATE SET review_class=excluded.review_class, "
                "state=excluded.state, updated_at=excluded.updated_at, precedent_json=excluded.precedent_json",
                (
                    precedent["precedent_id"],
                    precedent["decision_type"] or "other",
                    review_class,
                    precedent["state"],
                    existing["created_at"] if existing else now,
                    now,
                    json.dumps(precedent, sort_keys=True),
                ),
            )
        if not existing:
            self.store._audit(
                ACTOR,
                "precedent.created",
                "precedent",
                precedent["precedent_id"],
                {
                    "decision_hash": precedent["decision_hash"],
                    "contracts": [c["contract_id"] for c in contracts],
                    "clauses": len(clauses),
                    "review_class": review_class,
                },
            )
        precedent["created_at"] = existing["created_at"] if existing else now
        return precedent

    def refresh(self, force: bool = False) -> dict[str, int]:
        """Bring precedents in line with the decision record: one live precedent
        per authoritative decision; superseded decisions retire their precedent.

        Covers every decision (no page cap) and does nothing when the decision
        record has not changed since the last refresh. Runs on write paths
        (recording a decision, venue intake) and at startup, never on reads.
        """
        from .decision_records import get_service as get_decisions

        get_decisions(self.store)  # the decision table exists even on a fresh database
        with self.store.connect() as db:
            sig_row = db.execute(
                "SELECT COUNT(*) n, MAX(created_at) m, COUNT(supersedes) s FROM decision_records"
            ).fetchone()
            signature = (sig_row["n"], sig_row["m"], sig_row["s"])
            if not force and signature == getattr(self, "_refreshed", None):
                return {"built": 0, "retired": 0}
            decisions = [
                json.loads(r["decision_json"])
                for r in db.execute("SELECT decision_json FROM decision_records ORDER BY created_at").fetchall()
            ]
            superseded = {
                r["supersedes"]
                for r in db.execute("SELECT supersedes FROM decision_records WHERE supersedes IS NOT NULL").fetchall()
            }
            states = {r["precedent_id"]: r["state"] for r in db.execute("SELECT precedent_id, state FROM precedents")}
        built = retired = 0
        exceptions = None
        for d in decisions:
            state = states.get(d["decision_id"])
            if d["decision_id"] in superseded:
                if state == "active":
                    self._set_state(d["decision_id"], "superseded", {"reason": "decision superseded"})
                    retired += 1
                continue
            if state is None:
                exceptions = self._exceptions_by_work_item() if exceptions is None else exceptions
                self.build(d, exceptions)
                built += 1
        self._refreshed = signature
        return {"built": built, "retired": retired}

    def _set_state(self, precedent_id: str, state: str, details: dict[str, Any]) -> None:
        p = self.get(precedent_id)
        if not p:
            return
        p["state"] = state
        p.update({k: v for k, v in details.items() if k in {"overruled_by", "overrule_reason"}})
        with self.store.connect() as db:
            db.execute(
                "UPDATE precedents SET state=?, updated_at=?, precedent_json=? WHERE precedent_id=?",
                (state, utcnow(), json.dumps(p, sort_keys=True), precedent_id),
            )
            if state != "active":
                # Matches are derived; the audit chain keeps their history.
                db.execute("DELETE FROM precedent_matches WHERE precedent_id=?", (precedent_id,))
        self.store._audit(ACTOR, f"precedent.{state}", "precedent", precedent_id, details)

    def overrule(self, precedent_id: str, *, by_decision: str, reason: str, actor: str) -> None:
        """Prospective overrule: the old decision keeps governing its own cases,
        but stops being precedent for new ones."""
        p = self.get(precedent_id)
        if not p:
            raise ValueError(f"unknown precedent {precedent_id}")
        if p["state"] != "active":
            raise ValueError(f"precedent {precedent_id} is already {p['state']}")
        self._set_state(
            precedent_id,
            "overruled",
            {"overruled_by": by_decision, "overrule_reason": reason, "actor": actor},
        )

    def get(self, precedent_id: str) -> dict[str, Any] | None:
        with self.store.connect() as db:
            r = db.execute(
                "SELECT precedent_json, created_at FROM precedents WHERE precedent_id=?", (precedent_id,)
            ).fetchone()
        if not r:
            return None
        p = json.loads(r["precedent_json"])
        p["created_at"] = r["created_at"]
        return p

    def list(self, include_inactive: bool = False) -> list[dict[str, Any]]:
        sql = "SELECT precedent_json, created_at FROM precedents"
        if not include_inactive:
            sql += " WHERE state='active'"
        with self.store.connect() as db:
            rows = db.execute(sql + " ORDER BY created_at DESC").fetchall()
        out = []
        for r in rows:
            p = json.loads(r["precedent_json"])
            p["created_at"] = r["created_at"]
            out.append(p)
        return out

    # ---- matching ---------------------------------------------------------

    def corpus(self, extra: Iterable[dict[str, Any]] = ()) -> Corpus:
        """IDF over every contract Arbiter knows (latest versions) plus ``extra``."""
        extra = list(extra)
        with self.store.connect() as db:
            n = db.execute("SELECT COUNT(*) n, MAX(created_at) m FROM contract_versions").fetchone()
        key = (n["n"], n["m"], len(extra))
        if self._corpus is None or self._corpus_key != key or extra:
            seen: set[str] = set()
            rows: list[dict[str, Any]] = []
            for spec in self.store.list_contracts():
                if spec["contract_id"] in seen:
                    continue
                seen.add(spec["contract_id"])
                rows.append(
                    {"title": spec.get("title") or "", "rules": (spec.get("definition") or {}).get("yes_if") or ""}
                )
            corpus = Corpus(rows + extra)
            if extra:
                return corpus
            self._corpus, self._corpus_key = corpus, key
        return self._corpus

    def match(
        self,
        row: dict[str, Any],
        *,
        precedents: list[dict[str, Any]] | None = None,
        corpus: Corpus | None = None,
        template_sentences: Iterable[str] = (),
        min_tier: str = "related",
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Precedents that bear on ``row``, strongest first, each with its evidence."""
        precedents = self.list() if precedents is None else precedents
        if not precedents:
            return []
        corpus = corpus or self.corpus()
        templates = set(template_sentences)
        rv = corpus.vectors(row)
        cand = [(s, normalize_clause(s)) for s in sentences(row.get("rules") or "")]
        cand_vecs = [(s, n, corpus.clause_vector(n)) for s, n in cand if n not in templates]
        # Index candidate sentences by bigram: two clauses cannot be similar
        # without sharing a fair share of their word pairs, so only sentences
        # sharing >= CLAUSE_PREFILTER of a precedent clause's bigrams are scored.
        by_bigram: dict[str, list[int]] = {}
        for idx, (_, _, v) in enumerate(cand_vecs):
            for t in v:
                if "_" in t:
                    by_bigram.setdefault(t, []).append(idx)
        cid = row.get("contract_id") or f"{row.get('venue')}:{row.get('market_id')}"
        out: list[dict[str, Any]] = []
        for p in precedents:
            best_contract, best_c = 0.0, None
            for c in p.get("contracts") or []:
                s = corpus.similarity(rv, corpus.vectors(c))
                if s > best_contract:
                    best_contract, best_c = s, c
            best_clause, clause_pair = 0.0, None
            for pc in p.get("clauses") or []:
                if pc["normalized"] in templates:
                    continue  # standing fine print never carries a ruling
                pv = corpus.clause_vector(pc["normalized"])
                bigrams = [t for t in pv if "_" in t]
                shared: Counter = Counter(i for t in bigrams for i in by_bigram.get(t, ()))
                floor = max(1, int(CLAUSE_PREFILTER * len(bigrams)))
                for idx in [i for i, c in shared.items() if c >= floor]:
                    s, n, v = cand_vecs[idx]
                    sim = 1.0 if n == pc["normalized"] else cosine(pv, v)
                    if sim > best_clause:
                        best_clause, clause_pair = sim, {"precedent_clause": pc["text"], "contract_clause": s}
            if best_clause >= SAME_CLAUSE:
                tier = "same_clause"
            elif best_contract >= SAME_TEMPLATE:
                tier = "same_template"
            elif best_contract >= RELATED or best_clause >= RELATED:
                tier = "related"
            else:
                continue
            if TIERS.index(tier) > TIERS.index(min_tier):
                continue
            decided = {c["contract_id"] for c in p.get("contracts") or []}
            if cid in decided:
                relation = "decided"
            elif best_c and best_c.get("event_id") and best_c.get("event_id") == row.get("event_id"):
                relation = "same_event"
            elif best_c and best_c.get("series") == series_of(row):
                relation = "same_series"
            elif best_c and best_c.get("venue") != row.get("venue"):
                relation = "cross_venue"
            else:
                relation = "cross_event"
            reasons = []
            if clause_pair and best_clause >= RELATED:
                reasons.append(f"clause similarity {best_clause:.2f}")
            reasons.append(f"contract similarity {best_contract:.2f}")
            if best_c:
                reasons.append(f"closest decided contract: {best_c['contract_id']}")
            out.append(
                {
                    "precedent_id": p["precedent_id"],
                    "tier": tier,
                    "applies": tier in APPLICABLE,
                    "score": round(max(best_clause if tier == "same_clause" else 0.0, best_contract), 3),
                    "clause_similarity": round(best_clause, 3),
                    "contract_similarity": round(best_contract, 3),
                    "relation": relation,
                    "matched_clause": clause_pair if best_clause >= RELATED else None,
                    "closest_contract": {k: best_c.get(k) for k in ("contract_id", "title", "event_id")}
                    if best_c
                    else None,
                    "reasons": reasons,
                    "ruling": {
                        "decision_type": p.get("decision_type"),
                        "review_class": p.get("review_class"),
                        "question": p.get("question"),
                        "selection": p.get("selection"),
                        "governing_rule": p.get("governing_rule"),
                        "rationale": p.get("rationale"),
                        "decided_at": p.get("decided_at"),
                        "decided_by": p.get("decided_by"),
                        "contracts": len(p.get("contracts") or []),
                    },
                }
            )
        out.sort(key=lambda m: m["ruling"].get("decided_at") or "", reverse=True)
        out.sort(key=lambda m: (TIERS.index(m["tier"]), -m["score"]))
        return out[: max(1, limit)]

    def check_arrival(
        self,
        row: dict[str, Any],
        contract_id: str,
        *,
        template_sentences: Iterable[str] = (),
        corpus: Corpus | None = None,
        precedents: list[dict[str, Any]] | None = None,
        matches: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """Match a newly synced contract and record applicable precedents.
        Pass ``matches`` when the caller already matched this row."""
        row = dict(row, contract_id=contract_id)
        matches = (
            matches
            if matches is not None
            else [
                m
                for m in self.match(
                    row, precedents=precedents, corpus=corpus, template_sentences=template_sentences, limit=5
                )
                if m["relation"] != "decided"
            ]
        )
        now = utcnow()
        for m in matches:
            if not m["applies"]:
                continue
            with self.store.connect() as db:
                prior = db.execute(
                    "SELECT tier FROM precedent_matches WHERE contract_id=? AND precedent_id=?",
                    (contract_id, m["precedent_id"]),
                ).fetchone()
                db.execute(
                    "INSERT INTO precedent_matches(contract_id,precedent_id,tier,score,matched_at,match_json) "
                    "VALUES(?,?,?,?,?,?) ON CONFLICT(contract_id,precedent_id) DO UPDATE SET tier=excluded.tier, "
                    "score=excluded.score, match_json=excluded.match_json",
                    (contract_id, m["precedent_id"], m["tier"], m["score"], now, json.dumps(m, sort_keys=True)),
                )
            if not prior or prior["tier"] != m["tier"]:
                self.store._audit(
                    ACTOR,
                    "precedent.matched",
                    "contract",
                    contract_id,
                    {
                        "precedent_id": m["precedent_id"],
                        "tier": m["tier"],
                        "score": m["score"],
                        "relation": m["relation"],
                    },
                )
        return matches

    def matches_for(self, precedent_id: str) -> list[dict[str, Any]]:
        with self.store.connect() as db:
            rows = db.execute(
                "SELECT contract_id, tier, score, matched_at FROM precedent_matches WHERE precedent_id=? "
                "ORDER BY score DESC",
                (precedent_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    # ---- consistency, appeals ---------------------------------------------

    def rows_for_cases(self, case_ids: Iterable[str]) -> list[dict[str, Any]]:
        exceptions = self._exceptions_by_work_item()
        rows = []
        for case_id in case_ids:
            exc = exceptions.get(case_id)
            if exc and exc.get("contract_id"):
                row = self._contract_row(exc["contract_id"])
                if row:
                    rows.append(row)
        return rows

    def applicable(
        self,
        rows: list[dict[str, Any]],
        *,
        decision_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """Strongest applicable precedent per precedent id across ``rows``.
        Read-only: callers on write paths refresh first.

        A precedent never counts against a contract it decided itself
        (relation ``decided``), but a precedent from the same work pattern does
        apply to new contracts: the next event of a series often lands in the
        pattern whose earlier cases were decided."""
        precedents = [p for p in self.list() if not decision_type or p.get("decision_type") == decision_type]
        if not precedents or not rows:
            return []
        corpus = self.corpus()
        best: dict[str, dict[str, Any]] = {}
        for row in rows:
            for m in self.match(row, precedents=precedents, corpus=corpus, min_tier="same_template", limit=10):
                if m["relation"] == "decided":
                    continue
                m = dict(m, for_contract=row.get("contract_id"))
                cur = best.get(m["precedent_id"])
                if not cur or (TIERS.index(m["tier"]), -m["score"]) < (TIERS.index(cur["tier"]), -cur["score"]):
                    best[m["precedent_id"]] = m
        return sorted(best.values(), key=lambda m: (TIERS.index(m["tier"]), -m["score"]))

    def consistency(
        self,
        *,
        selection: str,
        rows: list[dict[str, Any]],
        decision_type: str | None,
        cited: Iterable[str] = (),
    ) -> dict[str, Any]:
        """Does ``selection`` agree with the precedent that applies here?

        Only the strongest applicable tier counts (a same-clause ruling outranks
        a same-template one). Within it:

        * ``novel``      no applicable precedent
        * ``follows``    agrees with an applicable precedent it cites
        * ``consistent`` agrees with one without citing it
        * ``divergent``  agrees with none: the operator must distinguish or overrule

        When the applicable precedents disagree among themselves (a ruling was
        distinguished earlier), ``conflicting`` lists both holdings.
        """
        cited = set(cited)
        found = self.applicable(rows, decision_type=decision_type)
        if not found:
            return {
                "status": "novel",
                "precedent": None,
                "selection_agreement": None,
                "conflicting": [],
                "applicable": [],
            }
        tier = found[0]["tier"]
        peers = [m for m in found if m["tier"] == tier]
        agreeing = [m for m in peers if agrees(selection, m["ruling"].get("selection") or "")]
        if agreeing:
            top = next((m for m in agreeing if m["precedent_id"] in cited), agreeing[0])
            status = "follows" if top["precedent_id"] in cited else "consistent"
        else:
            top = peers[0]
            status = "divergent"
        holdings: dict[str, list[str]] = {}
        for m in peers:
            key = next((k for k in holdings if agrees(k, m["ruling"].get("selection") or "")), None)
            holdings.setdefault(key or (m["ruling"].get("selection") or ""), []).append(m["precedent_id"])
        return {
            "status": status,
            "precedent": top,
            "selection_agreement": round(jaccard(selection, top["ruling"].get("selection") or ""), 3),
            "conflicting": [{"selection": k, "precedent_ids": v} for k, v in holdings.items()]
            if len(holdings) > 1
            else [],
            "peers": [m["precedent_id"] for m in peers],
            "peer_matches": peers,
            "applicable": found[:5],
        }

    def overrule_line(
        self, precedent_id: str, peers: list[dict[str, Any]], *, by_decision: str, reason: str, actor: str
    ) -> list[str]:
        """Overrule a holding: retire the named precedent and every applicable
        peer that holds the same ruling (the line of precedent). A peer that is
        no longer active (retired concurrently) is skipped, not an error."""
        named = next((m for m in peers if m["precedent_id"] == precedent_id), None)
        if not named:
            raise ValueError(f"{precedent_id} is not an applicable precedent here")
        holding = named["ruling"].get("selection") or ""
        retired = []
        for m in peers:
            if m["precedent_id"] == precedent_id or agrees(holding, m["ruling"].get("selection") or ""):
                current = self.get(m["precedent_id"])
                if not current or current.get("state") != "active":
                    continue
                self.overrule(m["precedent_id"], by_decision=by_decision, reason=reason, actor=actor)
                retired.append(m["precedent_id"])
        return retired

    def appeal_check(
        self, *, contract_id: str, requested_selection: str, grounds: str = "", actor: str = "operator"
    ) -> dict[str, Any]:
        """Check an appeal (a request for a different ruling on a contract) against
        the decision that governs the contract and against applicable precedent."""
        row = self._contract_row(contract_id)
        if not row:
            raise ValueError(f"unknown contract {contract_id}")
        governing = [
            p
            for p in self.list(include_inactive=True)
            if contract_id in {c["contract_id"] for c in p.get("contracts") or []}
        ]
        governing.sort(key=lambda p: p.get("decided_at") or "", reverse=True)
        applicable = [m for m in self.match(row, min_tier="same_template", limit=5) if m["relation"] != "decided"]
        ruling = governing[0] if governing else None
        basis = ruling or (
            applicable[0]["ruling"] | {"precedent_id": applicable[0]["precedent_id"]} if applicable else None
        )
        if not basis:
            verdict = "no_ruling"
            note = (
                "No governed decision or applicable precedent covers this contract yet; the appeal is a first ruling."
            )
        else:
            if agrees(requested_selection, basis.get("selection") or ""):
                verdict = "matches_ruling"
                note = "The requested outcome agrees with the governing ruling; nothing to change."
            else:
                verdict = "contradicts_ruling"
                note = (
                    "Granting this appeal departs from the governing ruling. It needs either facts that distinguish "
                    "this contract, or an explicit overrule that stops the ruling guiding future contracts."
                )
        result = {
            "contract_id": contract_id,
            "title": row.get("title"),
            "requested_selection": requested_selection,
            "grounds": grounds,
            "verdict": verdict,
            "note": note,
            "governing_decision": (
                {
                    k: ruling.get(k)
                    for k in ("precedent_id", "selection", "governing_rule", "rationale", "decided_at", "state")
                }
                if ruling
                else None
            ),
            "applicable_precedents": applicable,
            "options": (
                ["uphold", "distinguish", "overrule"] if verdict == "contradicts_ruling" else ["record ruling"]
            ),
            "checked_at": utcnow(),
        }
        result["check_hash"] = canonical_hash(result)
        self.store._audit(
            actor,
            "appeal.checked",
            "contract",
            contract_id,
            {"verdict": verdict, "check_hash": result["check_hash"], "governing": (ruling or {}).get("precedent_id")},
        )
        return result

    # ---- Ask Arbiter ------------------------------------------------------

    def _ask_idf(self) -> dict[str, float]:
        """Term weights over every contract Arbiter knows plus the precedents,
        cached until either changes."""
        with self.store.connect() as db:
            c = db.execute("SELECT COUNT(*) n, MAX(created_at) m FROM contract_versions").fetchone()
            q = db.execute("SELECT COUNT(*) n, MAX(updated_at) m FROM precedents").fetchone()
        key = (c["n"], c["m"], q["n"], q["m"])
        if getattr(self, "_ask_idf_key", None) == key:
            return self._ask_idf_cache
        docs = [
            set(ask_terms(f"{c.get('title') or ''} {(c.get('definition') or {}).get('yes_if') or ''}"))
            for c in self.store.list_contracts()
        ]
        docs += [set(ask_terms(_precedent_text(p))) for p in self.list()]
        df: Counter = Counter()
        for d in docs:
            df.update(d)
        n = len(docs)
        idf = {t: math.log((n + 1) / (c + 1)) + 1 for t, c in df.items()}
        idf["__max__"] = math.log(n + 1) + 1
        self._ask_idf_key, self._ask_idf_cache = key, idf
        return idf

    def ask(self, question: str, *, contract_id: str | None = None, limit: int = 3) -> dict[str, Any]:
        """Answer from the precedent record only, with citations. If nothing in
        the record covers the question, say so instead of guessing."""
        precedents = self.list()
        cites: list[dict[str, Any]] = []
        if contract_id:
            row = self._contract_row(contract_id)
            if row:
                for m in self.match(row, precedents=precedents, limit=limit):
                    cites.append({"precedent_id": m["precedent_id"], "why": m["tier"].replace("_", " "), "match": m})
        if not cites and precedents:
            idf = self._ask_idf()
            q = set(ask_terms(question))
            q_weight = sum(idf.get(t, idf["__max__"]) for t in q) or 1.0
            scored = []
            for p in precedents:
                doc = set(ask_terms(_precedent_text(p)))
                hit = q & doc
                coverage = sum(idf.get(t, idf["__max__"]) for t in hit) / q_weight
                if len(hit) >= 2 or (len(q) == 1 and hit):
                    scored.append((coverage, p["precedent_id"], sorted(hit)))
            scored.sort(reverse=True)
            for cov, pid, hit in scored[:limit]:
                if cov >= ASK_COVERAGE:
                    cites.append(
                        {
                            "precedent_id": pid,
                            "why": f"covers {cov:.0%} of the question ({', '.join(hit)})",
                            "match": None,
                        }
                    )
        by_id = {p["precedent_id"]: p for p in precedents}
        citations = []
        for c in cites:
            p = by_id.get(c["precedent_id"])
            if not p:
                continue
            clause = (c["match"] or {}).get("matched_clause") or (
                {"precedent_clause": p["clauses"][0]["text"]} if p.get("clauses") else None
            )
            citations.append(
                {
                    "precedent_id": p["precedent_id"],
                    "why": c["why"],
                    "selection": p.get("selection"),
                    "governing_rule": p.get("governing_rule"),
                    "rationale": p.get("rationale"),
                    "decided_at": p.get("decided_at"),
                    "contracts": [x["contract_id"] for x in p.get("contracts") or []][:5],
                    "contract_count": len(p.get("contracts") or []),
                    "clause": clause,
                    "matched_contracts": len(self.matches_for(p["precedent_id"])),
                }
            )
        if not citations:
            answer = (
                "Nothing in the governed record covers this yet. No precedent matches, so any ruling here would be "
                "a first decision."
            )
        else:
            top = citations[0]
            lines = [
                f"Precedent {top['precedent_id']} ({(top['decided_at'] or '')[:10]}, "
                f"{top['contract_count']} contract{'s' if top['contract_count'] != 1 else ''}) ruled: "
                f"“{top['selection']}”."
            ]
            if top.get("governing_rule"):
                lines.append(f"Governing rule: {top['governing_rule']}.")
            if top.get("rationale"):
                lines.append(f"Reasoning: {top['rationale']}")
            if top.get("clause") and top["clause"].get("precedent_clause"):
                lines.append(f"Clause ruled on: “{top['clause']['precedent_clause']}”")
            if len(citations) > 1:
                lines.append("Also relevant: " + ", ".join(c["precedent_id"] for c in citations[1:]) + ".")
            answer = " ".join(lines)
        return {
            "question": question,
            "contract_id": contract_id,
            "answer": answer,
            "citations": citations,
            "grounded": bool(citations),
            "method": "deterministic retrieval over the precedent record; no model generated this answer",
        }

    def posture(self) -> dict[str, Any]:
        with self.store.connect() as db:
            states = {r["state"]: r["n"] for r in db.execute("SELECT state, COUNT(*) n FROM precedents GROUP BY state")}
            matched = db.execute("SELECT COUNT(DISTINCT contract_id) n FROM precedent_matches").fetchone()["n"]
        return {
            "version": VERSION,
            "precedents": states,
            "contracts_matched": matched,
            "thresholds": {"same_clause": SAME_CLAUSE, "same_template": SAME_TEMPLATE, "related": RELATED},
            "boundary": "Precedents inform human judgment. They never record a decision or change an outcome.",
        }


_engine: PrecedentEngine | None = None


def get_engine(store) -> PrecedentEngine:
    global _engine
    if _engine is None or _engine.store is not store:
        _engine = PrecedentEngine(store)
    return _engine
