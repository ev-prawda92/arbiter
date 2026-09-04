#!/usr/bin/env python3
"""Arbiter v0.11 evidence worker.

Small production-shaped worker process that asks the Arbiter API for due
monitors. The API remains the authority for scheduling, backoff, idempotency,
and audit. Run this process under a supervisor/container in deployed envs.
"""
from __future__ import annotations
import argparse
import json
import os
import signal
import time
import urllib.error
import urllib.request

STOP = False

def _stop(*_):
    global STOP
    STOP = True

def call(base: str, key: str | None, limit: int) -> dict:
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if key:
        headers["X-Arbiter-Key"] = key
    req = urllib.request.Request(
        base.rstrip("/") + f"/api/evidence-poll-due?limit={limit}",
        data=b"{}", headers=headers, method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read()
        return json.loads(raw.decode()) if raw else {}

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default=os.environ.get("ARBITER_BASE_URL", "http://127.0.0.1:8000"))
    ap.add_argument("--api-key", default=os.environ.get("ARBITER_API_KEY"))
    ap.add_argument("--interval", type=int, default=int(os.environ.get("ARBITER_EVIDENCE_WORKER_INTERVAL", "30")))
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--once", action="store_true")
    args = ap.parse_args()
    if args.interval < 5:
        raise SystemExit("--interval must be >= 5 seconds")
    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)
    print(f"Arbiter evidence worker → {args.base_url} interval={args.interval}s")
    while not STOP:
        try:
            out = call(args.base_url, args.api_key, min(max(args.limit, 1), 100))
            print(json.dumps({"due": out.get("due", 0), "processed": out.get("processed", 0)}, sort_keys=True))
        except urllib.error.HTTPError as e:
            print(f"worker HTTP error {e.code}: {e.read().decode(errors='replace')}")
        except Exception as e:
            print(f"worker error: {e}")
        if args.once:
            break
        for _ in range(args.interval):
            if STOP:
                break
            time.sleep(1)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
