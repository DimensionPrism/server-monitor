#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PID_PATH="$REPO_ROOT/logs/dashboard.pid"
STOPPED=0

stop_pid_if_running() {
  local pid_text="$1"
  if [[ "$pid_text" =~ ^[0-9]+$ ]] && kill -0 "$pid_text" 2>/dev/null; then
    kill "$pid_text" 2>/dev/null || true
    STOPPED=1
  fi
}

if [[ -n "${MAINPID:-}" ]]; then
  stop_pid_if_running "$MAINPID"
fi

if [[ -f "$PID_PATH" ]]; then
  PID_TEXT="$(tr -d '[:space:]' <"$PID_PATH")"
  stop_pid_if_running "$PID_TEXT"
  rm -f "$PID_PATH"
fi

if [[ "$STOPPED" -eq 0 ]]; then
  echo "No dashboard process found."
  exit 0
fi

echo "Dashboard stop signal sent."
