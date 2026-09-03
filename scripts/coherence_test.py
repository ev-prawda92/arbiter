#!/usr/bin/env python3
"""API-driven coherence smoke test for Arbiter v0.9.x.

Runs the canonical READY / REVIEW / BLOCK paths against a running Arbiter API,
then checks durable case reruns, template creation, cross-surface endpoints,
audit-chain integrity, developer docs, and the development benchmark baseline.

Usage:
    python3 scripts/coherence_test.py
    python3 scripts/coherence_test.py --base-url http://127.0.0.1:8001
    ARBITER_API_KEY=arb_... python3 scripts/coherence_test.py
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURE = ROOT / "tests" / "fixtures" / "coherence_cases.json"


class TestFailure(Exception):
    pass


class Client:
    def __init__(self, base_url: str, api_key: str | None = None, timeout: float = 20.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def request(self, method: str, path: str, body: dict[str, Any] | None = None) -> tuple[int, Any]:
        data = json.dumps(body).encode() if body is not None else None
        headers = {"Accept": "application/json"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        if self.api_key:
            headers["X-Arbiter-Key"] = self.api_key
        req = urllib.request.Request(self.base_url + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
                ctype = resp.headers.get("content-type", "")
                if "json" in ctype:
                    return resp.status, json.loads(raw.decode() or "{}")
                return resp.status, raw.decode(errors="replace")
        except urllib.error.HTTPError as e:
            raw = e.read()
            try:
                payload = json.loads(raw.decode())
            except Exception:
                payload = raw.decode(errors="replace")
            return e.code, payload
        except urllib.error.URLError as e:
            raise TestFailure(f"Could not reach {self.base_url}: {e.reason}") from e

    def get(self, path: str) -> Any:
        status, payload = self.request("GET", path)
        if status != 200:
            raise TestFailure(f"GET {path} returned {status}: {payload}")
        return payload

    def post(self, path: str, body: dict[str, Any] | None = None) -> Any:
        status, payload = self.request("POST", path, body or {})
        if status != 200:
            raise TestFailure(f"POST {path} returned {status}: {payload}")
        return payload


class Runner:
    def __init__(self, client: Client, fixture: dict[str, Any], run_benchmark: bool = True):
        self.client = client
        self.fixture = fixture
        self.run_benchmark = run_benchmark
        self.passed = 0
        self.failed = 0
        self.created_cases: dict[str, dict[str, Any]] = {}

    def check(self, label: str, condition: bool, detail: str = "") -> None:
        if condition:
            self.passed += 1
            print(f"[PASS] {label}")
        else:
            self.failed += 1
            suffix = f" — {detail}" if detail else ""
            print(f"[FAIL] {label}{suffix}")

    def require(self, label: str, condition: bool, detail: str = "") -> None:
        self.check(label, condition, detail)
        if not condition:
            raise TestFailure(label + (f": {detail}" if detail else ""))

    @staticmethod
    def authorities(compilation: dict[str, Any]) -> list[str]:
        spec = compilation.get("proposed_spec") or compilation.get("resolution_specification") or compilation.get("specification") or compilation.get("spec") or {}
        return list(spec.get("authority_ids") or compilation.get("authority_ids") or [])

    @staticmethod
    def definition_type(compilation: dict[str, Any]) -> str | None:
        spec = compilation.get("proposed_spec") or compilation.get("resolution_specification") or compilation.get("specification") or compilation.get("spec") or {}
        definition = spec.get("definition") or compilation.get("definition") or {}
        return definition.get("type")

    def analyze_case(self, case: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "question": case["question"],
            "criteria": case["criteria"],
            "use_llm": False,
            "actor": "test:coherence-harness",
        }
        out = self.client.post("/api/analyze", payload)
        compilation = out.get("compilation") or {}
        resolution = out.get("resolution") or {}
        saved = out.get("case") or {}
        key = case["key"]

        self.check(f"{key}: compiler={case['expected_compiler']}", compilation.get("status") == case["expected_compiler"], str(compilation.get("status")))
        self.check(f"{key}: resolution={case['expected_resolution']}", resolution.get("outcome") == case["expected_resolution"], str(resolution.get("outcome")))
        self.check(f"{key}: case persisted", bool(saved.get("case_id")), str(saved))

        exp = case.get("expected") or {}
        unresolved = set(compilation.get("unresolved_fields") or [])
        authorities = self.authorities(compilation)
        dtype = self.definition_type(compilation)
        if "authority_id" in exp:
            self.check(f"{key}: authority {exp['authority_id']}", exp["authority_id"] in authorities, str(authorities))
        if "forbidden_authority_id" in exp:
            self.check(f"{key}: conflicted authority not trusted", exp["forbidden_authority_id"] not in authorities, str(authorities))
        if "definition_type" in exp:
            self.check(f"{key}: definition {exp['definition_type']}", dtype == exp["definition_type"], str(dtype))
        if exp.get("unresolved_fields") == []:
            self.check(f"{key}: no unresolved fields", not unresolved, str(sorted(unresolved)))
        for field in exp.get("unresolved_fields_contains", []):
            self.check(f"{key}: unresolved contains {field}", field in unresolved, str(sorted(unresolved)))
        if "gate" in exp:
            self.check(f"{key}: gate {exp['gate']}", resolution.get("gate") == exp["gate"], str(resolution.get("gate")))

        self.created_cases[key] = out
        return out

    def test_case_rerun(self) -> None:
        case = next(c for c in self.fixture["cases"] if c["key"] == "review_fed")
        first = self.created_cases["review_fed"]
        first_case = first["case"]
        case_id = first_case["case_id"]
        payload = {
            "question": case["question"],
            "criteria": case["rerun_criteria"],
            "case_id": case_id,
            "use_llm": False,
            "actor": "test:coherence-harness",
        }
        rerun = self.client.post("/api/analyze", payload)
        self.check("case rerun preserves case_id", (rerun.get("case") or {}).get("case_id") == case_id, str(rerun.get("case")))
        self.check("case rerun improves Fed contract to READY", (rerun.get("compilation") or {}).get("status") == "READY", str((rerun.get("compilation") or {}).get("status")))
        detail = self.client.get(f"/api/cases/{case_id}").get("case") or {}
        runs = detail.get("runs") or []
        self.check("case rerun appends run history", len(runs) >= 2, f"runs={len(runs)}")
        self.check("case retains latest edited criteria", detail.get("criteria") == case["rerun_criteria"], str(detail.get("criteria")))

        template_name = f"Coherence Fed Template {int(time.time())}"
        template = self.client.post(f"/api/cases/{case_id}/template", {"name": template_name, "actor": "test:coherence-harness"}).get("template") or {}
        self.check("template created from saved case", bool(template.get("template_id")), str(template))
        templates = self.client.get("/api/templates").get("templates") or []
        self.check("template visible in registry", any(t.get("template_id") == template.get("template_id") for t in templates), f"templates={len(templates)}")

    def test_cross_surface(self) -> None:
        for path, label in [
            ("/api/health", "health"),
            ("/api/cases", "cases registry"),
            ("/api/templates", "templates registry"),
            ("/api/authorities", "authority registry"),
            ("/api/infrastructure", "infrastructure summary"),
            ("/api/overview", "executive overview"),
            ("/api/work-queue", "work queue"),
            ("/api/portfolio", "portfolio intelligence"),
            ("/api/policy", "policy"),
            ("/api/developer", "developer manifest"),
        ]:
            status, payload = self.client.request("GET", path)
            self.check(f"cross-surface: {label} loads", status == 200, f"HTTP {status}: {payload}")

        # Docs surfaces are intentionally HTML/JSON, not normal API payloads.
        for path, label in [("/docs", "Swagger"), ("/redoc", "ReDoc"), ("/openapi.json", "OpenAPI")]:
            status, payload = self.client.request("GET", path)
            self.check(f"developer docs: {label} loads", status == 200, f"HTTP {status}")

    def test_audit(self) -> None:
        audit = self.client.get("/api/audit?limit=500")
        chain = audit.get("chain") or {}
        events = audit.get("events") or []
        self.check("audit chain verifies", chain.get("ok") is True, str(chain))
        self.check("coherence activity is audited", any(e.get("actor") == "test:coherence-harness" for e in events), f"events={len(events)}")

    def test_benchmark(self) -> None:
        if self.run_benchmark:
            result = self.client.post("/api/benchmark/run", {})
        else:
            result = self.client.get("/api/benchmark")
        metrics = result.get("metrics") or {}
        expected = {
            "total_cases": 90,
            "valid_cases": 90,
            "mutation_cases": 70,
            "clean_cases": 20,
        }
        for key, value in expected.items():
            self.check(f"benchmark: {key}={value}", metrics.get(key) == value, str(metrics.get(key)))
        self.check("benchmark: defect detection baseline", metrics.get("defect_detection_rate") == 1.0, str(metrics.get("defect_detection_rate")))
        self.check("benchmark: clean false-positive baseline", metrics.get("clean_false_positive_rate") == 0.0, str(metrics.get("clean_false_positive_rate")))

    def run(self) -> int:
        print(f"Arbiter coherence harness → {self.client.base_url}")
        print("NOTE: this creates test cases/templates in the local Arbiter database.\n")
        health_status, health = self.client.request("GET", "/api/health")
        self.require("API reachable", health_status == 200, f"HTTP {health_status}: {health}")

        for case in self.fixture["cases"]:
            try:
                self.analyze_case(case)
            except Exception as e:
                self.failed += 1
                print(f"[ERROR] {case['key']}: {e}")

        try:
            self.test_case_rerun()
        except Exception as e:
            self.failed += 1
            print(f"[ERROR] durable case/template workflow: {e}")

        try:
            self.test_cross_surface()
        except Exception as e:
            self.failed += 1
            print(f"[ERROR] cross-surface checks: {e}")

        try:
            self.test_audit()
        except Exception as e:
            self.failed += 1
            print(f"[ERROR] audit checks: {e}")

        try:
            self.test_benchmark()
        except Exception as e:
            self.failed += 1
            print(f"[ERROR] benchmark checks: {e}")

        total = self.passed + self.failed
        print("\n" + "=" * 64)
        print(f"RESULT: {self.passed}/{total} checks passed; {self.failed} failed")
        if self.failed:
            print("COHERENCE: FAIL")
            return 1
        print("COHERENCE: PASS")
        return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Run Arbiter API coherence checks")
    p.add_argument("--base-url", default=os.environ.get("ARBITER_BASE_URL", "http://127.0.0.1:8000"))
    p.add_argument("--api-key", default=os.environ.get("ARBITER_API_KEY"))
    p.add_argument("--fixture", default=str(DEFAULT_FIXTURE))
    p.add_argument("--skip-benchmark-run", action="store_true", help="Read the latest benchmark result instead of rerunning it")
    args = p.parse_args()

    fixture = json.loads(Path(args.fixture).read_text())
    client = Client(args.base_url, args.api_key)
    return Runner(client, fixture, run_benchmark=not args.skip_benchmark_run).run()


if __name__ == "__main__":
    sys.exit(main())
