#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

checks: list[tuple[str, bool]] = []


def chk(name: str, condition: bool) -> None:
    checks.append((name, bool(condition)))
    print(f"[{'PASS' if condition else 'FAIL'}] {name}")


def req(base: str, path: str, method: str = "GET", body=None, key: str | None = None):
    headers = {"Content-Type": "application/json"}
    data = json.dumps(body).encode() if body is not None else None
    if key:
        headers["X-Arbiter-Key"] = key
    request = urllib.request.Request(base + path, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--api-key")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]

    posture = req(args.base_url, "/api/deployment/posture", key=args.api_key)
    chk("deployment posture loads", posture.get("version") == "0.22.0")
    chk("deployment IaC inventory is complete", posture.get("deployment_iac_complete") is True)
    chk("deployment is not falsely claimed proven", posture.get("deployment_proven") is False)
    chk("required artifact inventory is substantial", len(posture.get("artifacts", [])) >= 8)
    chk("all required deployment artifacts are present", all(x.get("present") for x in posture.get("artifacts", [])))

    requirements = posture.get("requirements", {})
    chk("managed PostgreSQL is required", "managed_postgresql" in requirements)
    chk("managed object storage is required", "managed_object_storage" in requirements)
    chk("multi-instance service is required", "multi_instance_service" in requirements)
    chk("TLS ingress is required", "tls_ingress" in requirements)

    self_test = req(args.base_url, "/api/deployment/self-test", "POST", {}, args.api_key)
    chk("deployment self-test passes", self_test.get("ok") is True)
    chk("deployment self-test has zero settlement authority", self_test.get("settlement_authority") is False)

    developer = req(args.base_url, "/api/developer", key=args.api_key)
    chk("developer manifest exposes deployment readiness", developer.get("deployment_readiness", {}).get("version") == "0.22.0")

    infrastructure = req(args.base_url, "/api/infrastructure", key=args.api_key)
    chk("infrastructure summary exposes deployment readiness", infrastructure.get("deployment_readiness", {}).get("version") == "0.22.0")

    docker = (root / "Dockerfile").read_text()
    terraform = (root / "deploy/aws/main.tf").read_text()
    chk("container runs as non-root Arbiter user", "USER arbiter" in docker)
    chk("Terraform declares Multi-AZ RDS", bool(re.search(r"multi_az\s*=\s*true", terraform)))
    chk(
        "Terraform enforces at least two service tasks",
        bool(re.search(r"desired_count\s*=\s*max\(var\.desired_count,\s*2\)", terraform)),
    )
    chk("Terraform enables KMS key rotation", bool(re.search(r"enable_key_rotation\s*=\s*true", terraform)))

    static = subprocess.run(
        [sys.executable, str(root / "scripts/terraform_static_check.py")],
        capture_output=True,
        text=True,
    )
    if static.stdout:
        print(static.stdout.rstrip())
    if static.stderr:
        print(static.stderr.rstrip())
    chk("offline Terraform syntax-shape check passes", static.returncode == 0)

    chk("health reports v0.26+", req(args.base_url, "/api/health", key=args.api_key).get("version", "") >= "0.26.0")

    total = len(checks)
    passed = sum(value for _, value in checks)
    print("\n" + "=" * 64)
    print(f"RESULT: {passed}/{total} checks passed; {total - passed} failed")
    if passed != total:
        raise SystemExit(1)
    print("DEPLOYMENT VALIDATION GATE: PASS")


if __name__ == "__main__":
    main()
