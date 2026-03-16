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

mkdir -p "$LOGS_DIR"

if ss -ltn "sport = :$PORT" 2>/dev/null | tail -n +2 | grep -q .; then
  echo "Port $PORT is already in use."
  echo "If this is the dashboard, open: http://127.0.0.1:$PORT"
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

if [[ "$FOREGROUND" -eq 1 ]]; then
  cd "$REPO_ROOT"
  echo "Starting dashboard in foreground on http://127.0.0.1:$PORT"
  exec "$PYTHON_PATH" "${UVICORN_ARGS[@]}"
fi

cd "$REPO_ROOT"
nohup "$PYTHON_PATH" "${UVICORN_ARGS[@]}" >"$LOG_PATH" 2>"$ERROR_LOG_PATH" < /dev/null &
DASHBOARD_PID=$!
echo "$DASHBOARD_PID" >"$PID_PATH"

echo "Dashboard started in background."
echo "PID: $DASHBOARD_PID"
echo "URL: http://127.0.0.1:$PORT"
echo "Log: $LOG_PATH"
echo "Error Log: $ERROR_LOG_PATH"
