"""Arbiter composed application entrypoint.

v0.34 mounts the Decision Operations router around the existing main application
without destabilizing the long-lived main.py surface. New deployments should run
`uvicorn app.server:app`; legacy `app.main:app` remains available during migration.
"""

from __future__ import annotations

from .main import app, _workflow_payload, resolution_store
from . import developer, decision_api, decision_records

# Ensure the durable DecisionRecord table exists before the first request.
decision_records.get_service(resolution_store)

app.include_router(
    decision_api.build_router(
        resolution_store=resolution_store,
        workflow_builder=_workflow_payload,
        require_scope=developer.require_scope,
    )
)

# main.py mounts the built frontend as a catch-all StaticFiles app at "/".
# Starlette matches routes in registration order, so anything registered after
# that mount (the decision API above) would be shadowed and return 404. Keep
# every Mount last so API routes always win.
from starlette.routing import Mount  # noqa: E402

_mounts = [r for r in app.router.routes if isinstance(r, Mount)]
for _mount in _mounts:
    app.router.routes.remove(_mount)
    app.router.routes.append(_mount)
