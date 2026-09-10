#!/usr/bin/env python3
"""Smoke/regression gate for the standalone Arbiter public Resolution API."""
from __future__ import annotations

import argparse
import json
import sys
from urllib import error, request


def call(base_url: str, method: str, path: str, body=None, headers=None):
    data = None
    req_headers = {"Accept": "application/json", **(headers or {})}
    if body is not None:
        data = json.dumps(body).encode()
        req_headers["Content-Type"] = "application/json"
    req = request.Request(base_url.rstrip("/") + path, data=data, headers=req_headers, method=method)
    try:
        with request.urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read().decode())
            return resp.status, payload
    except error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            payload = json.loads(raw)
        except Exception:
            payload = {"raw": raw}
        return exc.code, payload


def require(name: str, condition: bool, detail=""):
    if condition:
        print(f"[PASS] {name}")
        return
    print(f"[FAIL] {name}{': ' + detail if detail else ''}")
    raise SystemExit(1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8001")
    ap.add_argument("--api-key", default=None)
    args = ap.parse_args()

    auth_headers = {"X-Arbiter-Key": args.api_key} if args.api_key else {}

    status, health = call(args.base_url, "GET", "/health")
    require("health endpoint", status == 200 and health.get("ok") is True, str(health))
    require("public API is non-settlement-authority", health.get("settlement_authority") is False, str(health))

    contract = {
        "contract_id": "API-GATE-WEATHER-001",
        "title": "Will NOAA report a temperature of at least 80°F on September 10, 2026?",
        "rules": "Resolve YES if NOAA reports a temperature of at least 80°F at 12:00 EST on September 10, 2026. Resolve NO otherwise.",
    }

    status, compiled = call(args.base_url, "POST", "/v1/contracts/compile", contract, auth_headers)
    require("compile request succeeds", status == 200, str(compiled))
    require("compiler returns READY", compiled.get("governance_status") == "READY", str(compiled))
    spec_hash = compiled.get("compilation", {}).get("proposed_spec")

    yes_body = {
        **contract,
        "evidence": {
            "observed_value": 82,
            "unit": "°F",
            "authority": "NOAA",
            "source_url": "https://www.weather.gov/",
            "raw_sha256": "sha256:api-gate-weather-yes",
        },
    }
    yes_headers = {**auth_headers, "Idempotency-Key": "api-gate-weather-yes-001"}
    status, yes = call(args.base_url, "POST", "/v1/contracts/resolve", yes_body, yes_headers)
    require("YES resolution succeeds", status == 200, str(yes))
    require("YES verdict", yes.get("verdict") == "YES", str(yes))
    require("YES governance READY", yes.get("governance_status") == "READY", str(yes))
    require("YES evidence sufficient", yes.get("evidence_status") == "SUFFICIENT", str(yes))
    require("YES avoids human review", yes.get("requires_human_review") is False, str(yes))

    no_body = {
        **contract,
        "evidence": {
            "observed_value": 77,
            "unit": "°F",
            "authority": "NOAA",
            "source_url": "https://www.weather.gov/",
            "raw_sha256": "sha256:api-gate-weather-no",
        },
    }
    no_headers = {**auth_headers, "Idempotency-Key": "api-gate-weather-no-001"}
    status, no = call(args.base_url, "POST", "/v1/contracts/resolve", no_body, no_headers)
    require("NO resolution succeeds", status == 200, str(no))
    require("NO verdict", no.get("verdict") == "NO", str(no))
    require("NO governance READY", no.get("governance_status") == "READY", str(no))
    require("NO evidence sufficient", no.get("evidence_status") == "SUFFICIENT", str(no))

    hold_headers = {**auth_headers, "Idempotency-Key": "api-gate-weather-hold-001"}
    status, hold = call(args.base_url, "POST", "/v1/contracts/resolve", contract, hold_headers)
    require("HOLD resolution succeeds", status == 200, str(hold))
    require("HOLD verdict", hold.get("verdict") == "HOLD", str(hold))
    require("HOLD contract remains READY", hold.get("governance_status") == "READY", str(hold))
    require("HOLD evidence insufficient", hold.get("evidence_status") == "INSUFFICIENT", str(hold))
    require("HOLD requires human review", hold.get("requires_human_review") is True, str(hold))

    status, replay = call(args.base_url, "POST", "/v1/contracts/resolve", no_body, no_headers)
    require("idempotent replay succeeds", status == 200, str(replay))
    require("idempotent replay preserves resolution id", replay.get("resolution_id") == no.get("resolution_id"), str(replay))

    conflict_body = {
        **contract,
        "evidence": {
            "observed_value": 76,
            "unit": "°F",
            "authority": "NOAA",
            "source_url": "https://www.weather.gov/",
            "raw_sha256": "sha256:api-gate-weather-conflict",
        },
    }
    status, conflict = call(args.base_url, "POST", "/v1/contracts/resolve", conflict_body, no_headers)
    require("idempotency key conflict rejected", status == 409, str(conflict))

    resolution_id = yes.get("resolution_id")
    status, fetched = call(args.base_url, "GET", f"/v1/resolutions/{resolution_id}", headers=auth_headers)
    require("resolution retrieval succeeds", status == 200, str(fetched))
    require("retrieved resolution id matches", fetched.get("resolution_id") == resolution_id, str(fetched))

    status, verified = call(
        args.base_url,
        "POST",
        "/v1/contracts/verify",
        {"resolution_id": resolution_id},
        auth_headers,
    )
    require("resolution verification succeeds", status == 200 and verified.get("verified") is True, str(verified))

    status, audit = call(args.base_url, "GET", f"/v1/audit/{resolution_id}", headers=auth_headers)
    require("resolution audit succeeds", status == 200, str(audit))
    require("audit chain valid", audit.get("chain", {}).get("ok") is True, str(audit))

    print("PUBLIC API GATE: PASS")


if __name__ == "__main__":
    main()
