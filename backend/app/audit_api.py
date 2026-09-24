"""FastAPI router for the v0.41 audit trail (auditor-facing, read-only except
anchoring and export, which are themselves recorded in the chain)."""

from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from . import audit_engagement, audit_trail


class AnchorIn(BaseModel):
    note: str = ""


class EngagementIn(BaseModel):
    name: str
    period_from: str
    period_to: str
    auditor_public_key: str


class SampleIn(BaseModel):
    population: str = "decisions"
    size: int = 25


class TestIn(BaseModel):
    item_id: str
    result: str
    note: str = ""


class FindingIn(BaseModel):
    title: str
    severity: str = "medium"
    description: str = ""
    item_ids: list[str] = []


class PrepareIn(BaseModel):
    opinion: str


class SignIn(BaseModel):
    opinion: str
    report_hash: str
    signature: str


def _actor(auth: dict[str, Any] | None) -> str:
    principal = (auth or {}).get("principal_id")
    if not principal:
        raise HTTPException(401, "this action needs an identified principal")
    return principal


def build_router(*, resolution_store, require_scope: Callable[[str], Any]) -> APIRouter:
    router = APIRouter(tags=["Audit"])
    read = Depends(require_scope("audit:read"))
    # Anchoring and exporting write to the chain, so they need their own scope.
    export = Depends(require_scope("audit:export"))

    def trail():
        return audit_trail.get_trail(resolution_store)

    @router.get("/api/audit/overview")
    def overview(auth=read):
        return trail().overview()

    @router.get("/api/audit/log")
    def log(
        q: str = "",
        actor: str = "",
        action: str = "",
        stage: str = "",
        object_id: str = "",
        since: str = "",
        until: str = "",
        limit: int = 100,
        offset: int = 0,
        auth=read,
    ):
        return trail().search(
            q=q,
            actor=actor,
            action=action,
            stage=stage,
            object_id=object_id,
            since=since,
            until=until,
            limit=limit,
            offset=offset,
        )

    @router.get("/api/audit/contracts")
    def contracts(q: str = "", auth=read):
        """Contracts an auditor can trace, most recently changed first."""
        seen: dict[str, dict[str, Any]] = {}
        for spec in resolution_store.list_contracts():
            cid = spec["contract_id"]
            if cid in seen:
                continue
            title = spec.get("title") or ""
            if q and q.lower() not in f"{cid} {title}".lower():
                continue
            seen[cid] = {"contract_id": cid, "title": title, "venue": (spec.get("metadata") or {}).get("venue")}
        with resolution_store.connect() as db:
            decided = {
                r["contract_id"]
                for r in db.execute(
                    "SELECT DISTINCT contract_id FROM evidence_exceptions WHERE contract_id IS NOT NULL"
                )
            }
        rows = list(seen.values())
        for r in rows:
            r["flagged"] = r["contract_id"] in decided
        rows.sort(key=lambda r: (not r["flagged"], r["contract_id"]))
        return {"contracts": rows[:300], "total": len(rows)}

    @router.get("/api/audit/lineage/{contract_id:path}")
    def lineage(contract_id: str, auth=read):
        try:
            return trail().lineage(contract_id)
        except KeyError as exc:
            raise HTTPException(404, "contract not found") from exc

    @router.get("/api/audit/exceptions")
    def exceptions(auth=read):
        return trail().exceptions()

    @router.get("/api/audit/anchors")
    def anchors(auth=read):
        return {"anchors": trail().anchors()}

    @router.post("/api/audit/anchor")
    def anchor(inp: AnchorIn, auth=export):
        try:
            return trail().anchor(actor=_actor(auth), note=inp.note)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @router.post("/api/audit/package")
    def package(auth=export):
        data, manifest = trail().package(actor=_actor(auth))
        stamp = (manifest["generated_at"] or "")[:19].replace(":", "").replace("-", "")
        return Response(
            content=data,
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="arbiter-audit-package-{stamp}.zip"',
                "X-Arbiter-Manifest-Hash": manifest["manifest_hash"],
                "X-Arbiter-Head-Hash": manifest["chain"]["head_hash"] or "",
            },
        )

    engage = Depends(require_scope("audit:engage"))

    def eng():
        return audit_engagement.get_engagements(resolution_store)

    def act(fn):
        try:
            return fn()
        except KeyError as exc:
            raise HTTPException(404, "engagement not found") from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc
        except audit_engagement.EngagementError as exc:
            raise HTTPException(422, str(exc)) from exc

    @router.get("/api/audit/engagements")
    def engagements(auth=read):
        return {"engagements": eng().list(), "populations": audit_engagement.POPULATIONS}

    @router.post("/api/audit/engagements")
    def open_engagement(inp: EngagementIn, auth=engage):
        return act(
            lambda: eng().open(
                actor=_actor(auth),
                name=inp.name,
                period_from=inp.period_from,
                period_to=inp.period_to,
                auditor_public_key=inp.auditor_public_key,
            )
        )

    @router.get("/api/audit/engagements/{engagement_id}")
    def get_engagement(engagement_id: str, auth=read):
        s = eng().get(engagement_id)
        if not s:
            raise HTTPException(404, "engagement not found")
        s["log_verified"] = eng().verify_log(engagement_id)
        s["preview"] = eng().preview(engagement_id)
        return s

    @router.get("/api/audit/engagements/{engagement_id}/log")
    def engagement_log(engagement_id: str, auth=read):
        return {"entries": eng().log(engagement_id), "verified": eng().verify_log(engagement_id)}

    @router.get("/api/audit/checks/{item_id}")
    def item_checks(item_id: str, auth=read):
        return {"item_id": item_id, "checks": eng().checks(item_id)}

    @router.post("/api/audit/engagements/{engagement_id}/sample")
    def sample(engagement_id: str, inp: SampleIn, auth=engage):
        return act(lambda: eng().sample(engagement_id, actor=_actor(auth), kind=inp.population, size=inp.size))

    @router.post("/api/audit/engagements/{engagement_id}/test")
    def test(engagement_id: str, inp: TestIn, auth=engage):
        return act(
            lambda: eng().test(engagement_id, actor=_actor(auth), item_id=inp.item_id, result=inp.result, note=inp.note)
        )

    @router.post("/api/audit/engagements/{engagement_id}/findings")
    def finding(engagement_id: str, inp: FindingIn, auth=engage):
        return act(
            lambda: eng().finding(
                engagement_id,
                actor=_actor(auth),
                title=inp.title,
                severity=inp.severity,
                description=inp.description,
                item_ids=inp.item_ids,
            )
        )

    @router.post("/api/audit/engagements/{engagement_id}/prepare")
    def prepare(engagement_id: str, inp: PrepareIn, auth=engage):
        """The report exactly as it will be signed; sign sign_message with your key."""
        return act(lambda: eng().draft(engagement_id, actor=_actor(auth), opinion=inp.opinion))

    @router.post("/api/audit/engagements/{engagement_id}/sign")
    def sign(engagement_id: str, inp: SignIn, auth=engage):
        return act(
            lambda: eng().sign(
                engagement_id,
                actor=_actor(auth),
                opinion=inp.opinion,
                report_hash=inp.report_hash,
                signature=inp.signature,
            )
        )

    return router
