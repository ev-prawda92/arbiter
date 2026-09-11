"""Dependency-free Arbiter Python SDK preview."""
from __future__ import annotations

import json
from urllib import request, parse


class Arbiter:
    def __init__(self, base_url="http://127.0.0.1:8000", api_key=None, timeout=15, tenant_id=None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.tenant_id = tenant_id

    def _call(self, method, path, body=None, headers=None):
        merged = {"Accept": "application/json"}
        if headers:
            merged.update(headers)
        data = None
        if body is not None:
            merged["Content-Type"] = "application/json"
            data = json.dumps(body).encode()
        if self.api_key:
            merged["X-Arbiter-Key"] = self.api_key
        if self.tenant_id:
            merged["X-Arbiter-Tenant"] = self.tenant_id
        req = request.Request(self.base_url + path, data=data, headers=merged, method=method)
        with request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode())

    # Existing application API
    def health(self):
        return self._call("GET", "/api/health")

    def developer(self):
        return self._call("GET", "/api/developer")

    def compile(self, contract_id, title, rules, contract_version=1, metadata=None):
        return self._call("POST", "/api/compile", {
            "contract_id": contract_id,
            "contract_version": contract_version,
            "title": title,
            "rules": rules,
            "metadata": metadata or {},
        })

    def contracts(self):
        return self._call("GET", "/api/contracts")

    def authorities(self):
        return self._call("GET", "/api/authorities")

    def evidence(self, contract_id=None):
        q = "?" + parse.urlencode({"contract_id": contract_id}) if contract_id else ""
        return self._call("GET", "/api/evidence" + q)

    def runs(self, contract_id=None):
        q = "?" + parse.urlencode({"contract_id": contract_id}) if contract_id else ""
        return self._call("GET", "/api/resolution-runs" + q)

    def overview(self):
        return self._call("GET", "/api/overview")

    def work_queue(self):
        return self._call("GET", "/api/work-queue")

    def portfolio(self):
        return self._call("GET", "/api/portfolio")

    def audit(self):
        return self._call("GET", "/api/audit")

    # Public v1 Resolution API
    def compile_v1(self, contract_id, title, rules, contract_version=1, exchange_profile="generic", metadata=None):
        return self._call("POST", "/v1/contracts/compile", {
            "contract_id": contract_id,
            "title": title,
            "rules": rules,
            "contract_version": contract_version,
            "exchange_profile": exchange_profile,
            "metadata": metadata or {},
        })

    def resolve_v1(self, contract_id, title, rules, evidence=None, contract_version=1,
                   exchange_profile="generic", metadata=None, idempotency_key=None):
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
        return self._call("POST", "/v1/contracts/resolve", {
            "contract_id": contract_id,
            "title": title,
            "rules": rules,
            "contract_version": contract_version,
            "exchange_profile": exchange_profile,
            "metadata": metadata or {},
            "evidence": evidence,
        }, headers=headers)

    def resolution_v1(self, resolution_id):
        return self._call("GET", f"/v1/resolutions/{parse.quote(resolution_id)}")

    def resolution_evidence_v1(self, resolution_id):
        return self._call("GET", f"/v1/evidence/{parse.quote(resolution_id)}")

    def verify_v1(self, resolution_id, expected_response_sha256=None):
        return self._call("POST", "/v1/contracts/verify", {
            "resolution_id": resolution_id,
            "expected_response_sha256": expected_response_sha256,
        })

    def resolution_audit_v1(self, resolution_id):
        return self._call("GET", f"/v1/audit/{parse.quote(resolution_id)}")
