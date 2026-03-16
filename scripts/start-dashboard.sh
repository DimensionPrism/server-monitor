#!/usr/bin/env bash
set -euo pipefail

PORT=8080
FOREGROUND=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --port|-p)
      PORT="$2"
      shift 2
      ;;
    --foreground|-f)
      FOREGROUND=1
      shift
      ;;
    *)
      echo "Unknown argument: $1" >&2
      echo "Usage: $0 [--port <port>] [--foreground]" >&2
      exit 1
      ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LOGS_DIR="$REPO_ROOT/logs"
LOG_PATH="$REPO_ROOT/logs/dashboard.log"
ERROR_LOG_PATH="$REPO_ROOT/logs/dashboard.stderr.log"
PID_PATH="$REPO_ROOT/logs/dashboard.pid"
PYTHON_PATH="$REPO_ROOT/.venv/bin/python"
STARTUP_ATTEMPTS=40
STARTUP_SLEEP_SECONDS=0.25
ERROR_TAIL_LINES=40

mkdir -p "$LOGS_DIR"

if ss -ltn "sport = :$PORT" 2>/dev/null | tail -n +2 | grep -q .; then
  echo "Port $PORT is already in use." >&2
  echo "If this is the dashboard, open: http://127.0.0.1:$PORT" >&2
  if [[ "$FOREGROUND" -eq 1 ]]; then
    exit 1
  fi
  exit 0
fi

if [[ ! -x "$PYTHON_PATH" ]]; then
  echo "Dashboard runtime not found at $PYTHON_PATH. Run 'uv sync' first." >&2
  exit 1
fi

UVICORN_ARGS=(
  -m
  uvicorn
  server_monitor.dashboard.main:build_dashboard_app
  --factory
  --host
  127.0.0.1
  --port
  "$PORT"
)

dashboard_health_check() {
  "$PYTHON_PATH" -c '
import json
import sys
import urllib.request

port = sys.argv[1]
url = f"http://127.0.0.1:{port}/health"
try:
    with urllib.request.urlopen(url, timeout=0.5) as response:
        if response.status != 200:
            raise RuntimeError("non-200 health response")
        payload = json.loads(response.read().decode("utf-8", errors="ignore"))
except Exception:
    raise SystemExit(1)

raise SystemExit(0 if payload.get("status") == "ok" else 1)
' "$PORT"
}

if [[ "$FOREGROUND" -eq 1 ]]; then
  cd "$REPO_ROOT"
  echo "$$" >"$PID_PATH"
  echo "Starting dashboard in foreground on http://127.0.0.1:$PORT"
  exec "$PYTHON_PATH" "${UVICORN_ARGS[@]}"
fi

cd "$REPO_ROOT"
nohup "$PYTHON_PATH" "${UVICORN_ARGS[@]}" >"$LOG_PATH" 2>"$ERROR_LOG_PATH" < /dev/null &
DASHBOARD_PID=$!
echo "$DASHBOARD_PID" >"$PID_PATH"

for ((attempt = 1; attempt <= STARTUP_ATTEMPTS; attempt++)); do
  if ! kill -0 "$DASHBOARD_PID" 2>/dev/null; then
    echo "Dashboard process exited before startup completed." >&2
    rm -f "$PID_PATH"
    if [[ -f "$ERROR_LOG_PATH" ]]; then
      echo "Recent stderr (last $ERROR_TAIL_LINES lines):" >&2
      tail -n "$ERROR_TAIL_LINES" "$ERROR_LOG_PATH" >&2 || true
    fi
    exit 1
  fi

  if dashboard_health_check; then
    echo "Dashboard started in background."
    echo "PID: $DASHBOARD_PID"
    echo "URL: http://127.0.0.1:$PORT"
    echo "Log: $LOG_PATH"
    echo "Error Log: $ERROR_LOG_PATH"
    exit 0
  fi

  sleep "$STARTUP_SLEEP_SECONDS"
done

echo "Dashboard process is running but /health did not become ready in time." >&2
kill "$DASHBOARD_PID" 2>/dev/null || true
rm -f "$PID_PATH"
if [[ -f "$ERROR_LOG_PATH" ]]; then
  echo "Recent stderr (last $ERROR_TAIL_LINES lines):" >&2
  tail -n "$ERROR_TAIL_LINES" "$ERROR_LOG_PATH" >&2 || true
fi
exit 1
