"""FastAPI router for the v0.41 audit trail (auditor-facing, read-only except
anchoring and export, which are themselves recorded in the chain)."""

from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from . import audit_trail


class AnchorIn(BaseModel):
    note: str = ""


def _actor(auth: dict[str, Any] | None) -> str:
    return (auth or {}).get("principal_id") or "auditor"


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

    return router
