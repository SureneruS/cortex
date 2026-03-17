#!/bin/bash
# Dashboard server watchdog — keeps backend (9400) and frontend (9401) alive
# Usage: ./scripts/dashboard-servers.sh

CORTEX_DIR="$(cd "$(dirname "$0")/.." && pwd)"
WEB_DIR="$CORTEX_DIR/web"
CHECK_INTERVAL=5

start_backend() {
  echo "[watchdog] Starting backend on :9400"
  cd "$CORTEX_DIR" && uv run uvicorn cortex.api:app --host 127.0.0.1 --port 9400 --reload &>/dev/null &
}

start_frontend() {
  echo "[watchdog] Starting frontend on :9401"
  cd "$WEB_DIR" && npm run dev -- --port 9401 &>/dev/null &
}

check_and_restart() {
  if ! curl -s --max-time 2 -o /dev/null http://localhost:9400/api/dashboard/resolved 2>/dev/null; then
    echo "[watchdog] Backend down — restarting"
    lsof -ti :9400 | xargs kill -9 2>/dev/null
    sleep 1
    start_backend
    sleep 3
  fi

  if ! curl -s --max-time 2 -o /dev/null http://localhost:9401/dashboard 2>/dev/null; then
    echo "[watchdog] Frontend down — restarting"
    lsof -ti :9401 | xargs kill -9 2>/dev/null
    sleep 1
    start_frontend
    sleep 3
  fi
}

# Initial start
check_and_restart

echo "[watchdog] Monitoring every ${CHECK_INTERVAL}s — Ctrl+C to stop"
while true; do
  sleep $CHECK_INTERVAL
  check_and_restart
done
