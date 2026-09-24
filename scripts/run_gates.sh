#!/usr/bin/env bash
# Run every Arbiter gate against fresh, throwaway state.
# Starts the app (:8000) and the public API (:8001) on temp databases, runs all
# gate scripts plus the full release gate, then stops both servers.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"
export ARBITER_POLICY_PATH="$TMP/policy.json"
PY="${PYTHON:-python3}"
pids=()
cleanup() { for p in "${pids[@]}"; do kill "$p" 2>/dev/null || true; done; rm -rf "$TMP"; }
trap cleanup EXIT

wait_for() {
  for _ in $(seq 1 30); do curl -fsS "$1" >/dev/null 2>&1 && return 0; sleep 1; done
  echo "server did not start: $1" >&2; return 1
}

cd "$ROOT/backend"
ARBITER_DATABASE_PATH="$TMP/main.db" "$PY" -m uvicorn app.server:app --host 127.0.0.1 --port 8000 >"$TMP/main.log" 2>&1 &
pids+=($!)
ARBITER_DATABASE_PATH="$TMP/public.db" "$PY" -m uvicorn app.public:app --host 127.0.0.1 --port 8001 >"$TMP/public.log" 2>&1 &
pids+=($!)
wait_for http://127.0.0.1:8000/api/health
wait_for http://127.0.0.1:8001/health
cd "$ROOT"

export ARBITER_DATABASE_PATH="$TMP/main.db"
failed=()
for gate in scripts/*_gate.py; do
  name="$(basename "$gate" .py)"
  [ "$name" = release_gate ] && continue
  db="$TMP/main.db"
  [ "$name" = public_api_gate ] && db="$TMP/public.db"  # tampers with its server's audit rows
  if ARBITER_DATABASE_PATH="$db" "$PY" "$gate" >"$TMP/$name.log" 2>&1; then
    echo "PASS  $name"
  else
    echo "FAIL  $name"; tail -5 "$TMP/$name.log"; failed+=("$name")
  fi
done
"$PY" scripts/release_gate.py | tail -1 || failed+=(release_gate)

if [ ${#failed[@]} -gt 0 ]; then echo "GATES FAILED: ${failed[*]}"; exit 1; fi
echo "ALL GATES PASS"
