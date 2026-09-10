#!/usr/bin/env python3
"""Smoke/regression gate for the standalone Arbiter public Resolution API."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib import error, request

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.resolution_infra import store as resolution_store  # noqa: E402


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


def tamper_json_column(resolution_id: str, column: str, mutate) -> str:
    """Mutate one persisted JSON blob for a controlled tamper-detection test."""
    if column not in {"request_json", "response_json"}:
        raise ValueError("unsupported tamper column")
    with resolution_store.connect() as db:
        row = db.execute(
            f"SELECT {column} FROM public_api_resolutions WHERE resolution_id=?",
            (resolution_id,),
        ).fetchone()
        if not row:
            raise RuntimeError(f"resolution not found for tamper test: {resolution_id}")
        original = str(row[column])
        payload = json.loads(original)
        mutate(payload)
        db.execute(
            f"UPDATE public_api_resolutions SET {column}=? WHERE resolution_id=?",
            (json.dumps(payload, sort_keys=True, default=str), resolution_id),
        )
    return original


def restore_json_column(resolution_id: str, column: str, original: str) -> None:
    with resolution_store.connect() as db:
        db.execute(
            f"UPDATE public_api_resolutions SET {column}=? WHERE resolution_id=?",
            (original, resolution_id),
        )


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
    require("request hash recomputes cleanly", verified.get("request_integrity", {}).get("matches") is True, str(verified))
    require("response hash recomputes cleanly", verified.get("response_integrity", {}).get("matches") is True, str(verified))
    require("embedded hashes match persisted pins", verified.get("embedded_hashes_match") is True, str(verified))

    status, wrong_expected = call(
        args.base_url,
        "POST",
        "/v1/contracts/verify",
        {"resolution_id": resolution_id, "expected_response_sha256": "sha256:not-the-real-digest"},
        auth_headers,
    )
    require("wrong expected response hash is rejected", status == 200 and wrong_expected.get("verified") is False, str(wrong_expected))
    require("expected hash mismatch is surfaced", wrong_expected.get("expected_response_matches") is False, str(wrong_expected))

    original_response = tamper_json_column(
        resolution_id,
        "response_json",
        lambda payload: payload.__setitem__("verdict", "NO" if payload.get("verdict") != "NO" else "YES"),
    )
    try:
        status, tampered_response = call(
            args.base_url,
            "POST",
            "/v1/contracts/verify",
            {"resolution_id": resolution_id},
            auth_headers,
        )
        require("tampered response is detected", status == 200 and tampered_response.get("verified") is False, str(tampered_response))
        require("response integrity failure is surfaced", tampered_response.get("response_integrity", {}).get("matches") is False, str(tampered_response))
    finally:
        restore_json_column(resolution_id, "response_json", original_response)

    status, restored_response = call(
        args.base_url,
        "POST",
        "/v1/contracts/verify",
        {"resolution_id": resolution_id},
        auth_headers,
    )
    require("response verifies after restoration", status == 200 and restored_response.get("verified") is True, str(restored_response))

    original_request = tamper_json_column(
        resolution_id,
        "request_json",
        lambda payload: payload.__setitem__("title", str(payload.get("title", "")) + " [tampered]"),
    )
    try:
        status, tampered_request = call(
            args.base_url,
            "POST",
            "/v1/contracts/verify",
            {"resolution_id": resolution_id},
            auth_headers,
        )
        require("tampered request is detected", status == 200 and tampered_request.get("verified") is False, str(tampered_request))
        require("request integrity failure is surfaced", tampered_request.get("request_integrity", {}).get("matches") is False, str(tampered_request))
    finally:
        restore_json_column(resolution_id, "request_json", original_request)

    status, restored_request = call(
        args.base_url,
        "POST",
        "/v1/contracts/verify",
        {"resolution_id": resolution_id},
        auth_headers,
    )
    require("request verifies after restoration", status == 200 and restored_request.get("verified") is True, str(restored_request))

    status, audit = call(args.base_url, "GET", f"/v1/audit/{resolution_id}", headers=auth_headers)
    require("resolution audit succeeds", status == 200, str(audit))
    require("audit chain valid", audit.get("chain", {}).get("ok") is True, str(audit))

    print("PUBLIC API GATE: PASS")


if __name__ == "__main__":
    main()
