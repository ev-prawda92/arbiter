"""Tiny dependency-free Arbiter Python SDK preview."""
from __future__ import annotations
import json
from urllib import request, parse

class Arbiter:
    def __init__(self, base_url="http://127.0.0.1:8000", api_key=None, timeout=15):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def _call(self, method, path, body=None):
        headers = {"Accept": "application/json"}
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode()
        if self.api_key:
            headers["X-Arbiter-Key"] = self.api_key
        req = request.Request(self.base_url + path, data=data, headers=headers, method=method)
        with request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode())

    def health(self): return self._call("GET", "/api/health")
    def developer(self): return self._call("GET", "/api/developer")
    def compile(self, contract_id, title, rules, contract_version=1, metadata=None):
        return self._call("POST", "/api/compile", {"contract_id": contract_id, "contract_version": contract_version, "title": title, "rules": rules, "metadata": metadata or {}})
    def contracts(self): return self._call("GET", "/api/contracts")
    def authorities(self): return self._call("GET", "/api/authorities")
    def evidence(self, contract_id=None):
        q = "?" + parse.urlencode({"contract_id": contract_id}) if contract_id else ""
        return self._call("GET", "/api/evidence" + q)
    def runs(self, contract_id=None):
        q = "?" + parse.urlencode({"contract_id": contract_id}) if contract_id else ""
        return self._call("GET", "/api/resolution-runs" + q)
    def overview(self): return self._call("GET", "/api/overview")
    def work_queue(self): return self._call("GET", "/api/work-queue")
    def portfolio(self): return self._call("GET", "/api/portfolio")
    def audit(self): return self._call("GET", "/api/audit")
