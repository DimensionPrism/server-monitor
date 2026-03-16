#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PID_PATH="$REPO_ROOT/logs/dashboard.pid"
PATTERN="server_monitor.dashboard.main:build_dashboard_app"
STOPPED=0

if [[ -f "$PID_PATH" ]]; then
  PID_TEXT="$(tr -d '[:space:]' <"$PID_PATH")"
  if [[ "$PID_TEXT" =~ ^[0-9]+$ ]] && kill -0 "$PID_TEXT" 2>/dev/null; then
    kill "$PID_TEXT" 2>/dev/null || true
    STOPPED=1
  fi
  rm -f "$PID_PATH"
fi

if pgrep -f "$PATTERN" >/dev/null 2>&1; then
  pkill -f "$PATTERN" || true
  STOPPED=1
fi

if [[ "$STOPPED" -eq 0 ]]; then
  echo "No dashboard process found."
  exit 0
fi

echo "Dashboard stop signal sent."
