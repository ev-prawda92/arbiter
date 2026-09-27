"""Read access control for the console API (v0.45).

Every /api/ request already needs a valid credential whenever authentication is
configured (main.enterprise_boundary). This adds least privilege for READS:
reading operational data (the queue, patterns, decisions, precedent, contracts,
Ask Arbiter) needs one of READ_SCOPES. The audit and engagement endpoints keep
their own audit:* scopes, so an auditor key reads the audit trail without also
reading the live queue unless it is granted operations:read.

Local-open development (no keys configured) is unaffected: its principal holds
admin:*.
"""

from __future__ import annotations

from fastapi import HTTPException
from fastapi.responses import JSONResponse

from . import demo_mode, developer

READ_SCOPES = frozenset({"operations:read", "operations:write", "admin:*"})

# Always reachable: liveness and posture probes, and "who am I" for any valid key.
PUBLIC_PATHS = frozenset({"/api/health", "/api/readiness", "/api/security-posture"})
ANY_PRINCIPAL_PATHS = frozenset({"/api/identity/whoami"})


def is_operational_read(method: str, path: str) -> bool:
    """A request that reads operational data and so needs a read scope."""
    if not path.startswith("/api/"):
        return False
    p = path.rstrip("/")
    if p in PUBLIC_PATHS or p in ANY_PRINCIPAL_PATHS or p.startswith("/api/audit"):
        return False
    if method.upper() == "GET":
        return True
    # Query-only POSTs (they take a body but write nothing) are reads too.
    return method.upper() == "POST" and p in demo_mode.READ_ONLY_POSTS


def can_read(scopes) -> bool:
    return bool(set(scopes or ()) & READ_SCOPES)


def install(app) -> None:
    @app.middleware("http")
    async def operational_read_scope(request, call_next):
        if is_operational_read(request.method, request.url.path):
            try:
                auth = developer.authenticate(
                    request.headers.get("X-Arbiter-Key"), request.headers.get("Authorization")
                )
            except HTTPException:
                # No valid credential: the enterprise boundary answers 401.
                return await call_next(request)
            if not can_read(auth.get("scopes")):
                return JSONResponse(
                    status_code=403,
                    content={
                        "detail": "this key cannot read operational data; it needs operations:read "
                        "(audit keys read the audit trail under /api/audit)"
                    },
                )
        return await call_next(request)
