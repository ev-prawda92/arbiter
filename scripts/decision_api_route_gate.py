#!/usr/bin/env python3
"""Release gate: the v0.34 decision API is reachable over HTTP.

The decision record / propagation gates exercise the Python services directly,
so they cannot notice when the web layer shadows a route. This gate boots the
composed app (app.server) and makes real requests.

Asserts (fail-closed):
  R1 no API route is registered after a catch-all Mount (static frontend)
  R2 GET /api/decisions answers 200 with a decisions list
  R3 GET /api/decision-context/<cluster> answers 200 for a live work pattern
  R4 an unknown work pattern answers the handler's own 404, not the static 404
  R5 the frontend pages are still served when a build is present
"""
from __future__ import annotations

import os
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND = os.path.join(ROOT, "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

_tmp = tempfile.mkdtemp(prefix="arbiter-route-gate-")
os.environ["ARBITER_DATABASE_PATH"] = os.path.join(_tmp, "arbiter.db")

from fastapi.testclient import TestClient  # noqa: E402
from starlette.routing import Mount  # noqa: E402

from app.server import app  # noqa: E402


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)
    print(f"[PASS] {message}")


def find_cluster_id(value):
    if isinstance(value, dict):
        cid = value.get("cluster_id")
        if isinstance(cid, str) and cid:
            return cid
        for v in value.values():
            found = find_cluster_id(v)
            if found:
                return found
    elif isinstance(value, list):
        for v in value:
            found = find_cluster_id(v)
            if found:
                return found
    return None


def main() -> None:
    routes = app.router.routes
    first_mount = next((i for i, r in enumerate(routes) if isinstance(r, Mount)), len(routes))
    # Anything that is not itself a Mount but sits after one is shadowed; this
    # includes routers added via include_router, which some FastAPI versions
    # register as a single wrapper object rather than individual APIRoutes.
    late = [getattr(r, "path", None) or type(r).__name__
            for r in routes[first_mount:] if not isinstance(r, Mount)]
    check(not late, f"no API route registered after the static mount (late: {late})")

    client = TestClient(app)

    r = client.get("/api/decisions")
    check(r.status_code == 200 and isinstance(r.json().get("decisions"), list),
          f"GET /api/decisions -> 200 (got {r.status_code})")

    overview = client.get("/api/overview")
    check(overview.status_code == 200, "GET /api/overview -> 200")
    cluster_id = find_cluster_id(overview.json())
    check(cluster_id is not None, "overview exposes at least one work pattern")

    r = client.get(f"/api/decision-context/{cluster_id}")
    check(r.status_code == 200 and "decision_prompt" in r.json(),
          f"GET /api/decision-context/{cluster_id} -> 200 with a decision prompt (got {r.status_code})")

    r = client.get("/api/decision-context/cluster_does_not_exist")
    check(r.status_code == 404 and r.json().get("detail") == "work pattern not found",
          "unknown work pattern gets the handler's 404, not the static-files 404")

    dist = os.path.join(BACKEND, "dist")
    if os.path.isdir(dist):
        for page in ("/", "/decision-workbench.html"):
            r = client.get(page)
            check(r.status_code == 200, f"GET {page} still served -> 200")
    else:
        print("[SKIP] frontend build not present; static page checks skipped")

    print("DECISION API ROUTE GATE: PASS")


if __name__ == "__main__":
    main()
