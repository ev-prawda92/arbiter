"""Read-only hosted demo mode (ARBITER_DEMO_MODE=1).

When enabled, every mutating request under /api/ is refused with 403 except a
short allowlist of POST endpoints that are pure queries (they take a JSON body
but write nothing to the database or the audit chain). Live venue and source
feeds are disabled, so the demo never calls out to the network.
"""

from __future__ import annotations

import os

from fastapi.responses import JSONResponse

DEMO_MESSAGE = "This is a read-only demo of Arbiter."
MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# POST endpoints the console calls only to read. Each is covered by the
# precedent gate's "reads write nothing" check or is a pure computation.
READ_ONLY_POSTS = frozenset(
    {
        "/api/ask",  # answers from recorded precedent; no writes (precedent gate P16)
        "/api/decisions/consistency",  # consistency preview before recording (P16)
        "/api/decision-precedents",  # ranks existing decisions; list query only
    }
)


def enabled() -> bool:
    return os.environ.get("ARBITER_DEMO_MODE", "").strip().lower() in {"1", "true", "yes", "on"}


def blocks(method: str, path: str) -> bool:
    return (
        enabled()
        and method.upper() in MUTATING_METHODS
        and path.startswith("/api/")
        and path.rstrip("/") not in READ_ONLY_POSTS
    )


def install(app) -> None:
    @app.middleware("http")
    async def demo_read_only(request, call_next):
        if blocks(request.method, request.url.path):
            return JSONResponse(status_code=403, content={"detail": DEMO_MESSAGE})
        return await call_next(request)
