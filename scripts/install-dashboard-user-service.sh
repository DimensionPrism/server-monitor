#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="server-monitor-dashboard.service"
PORT=8080
START_NOW=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --service-name)
      SERVICE_NAME="$2"
      shift 2
      ;;
    --port|-p)
      PORT="$2"
      shift 2
      ;;
    --start-now)
      START_NOW=1
      shift
      ;;
    *)
      echo "Unknown argument: $1" >&2
      echo "Usage: $0 [--service-name <name.service>] [--port <port>] [--start-now]" >&2
      exit 1
      ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
START_SCRIPT="$SCRIPT_DIR/start-dashboard.sh"
STOP_SCRIPT="$SCRIPT_DIR/stop-dashboard.sh"

if [[ ! -x "$START_SCRIPT" || ! -x "$STOP_SCRIPT" ]]; then
  echo "Missing executable scripts. Ensure start-dashboard.sh and stop-dashboard.sh are executable." >&2
  exit 1
fi

SYSTEMD_USER_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
SERVICE_PATH="$SYSTEMD_USER_DIR/$SERVICE_NAME"

mkdir -p "$SYSTEMD_USER_DIR"

cat >"$SERVICE_PATH" <<EOF
[Unit]
Description=Server Monitor Dashboard
After=network.target

[Service]
Type=simple
WorkingDirectory=$REPO_ROOT
ExecStart=$START_SCRIPT --port $PORT --foreground
ExecStop=$STOP_SCRIPT
Restart=on-failure
RestartSec=3

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable "$SERVICE_NAME"

echo "Installed user service: $SERVICE_NAME"
echo "Service file: $SERVICE_PATH"

if [[ "$START_NOW" -eq 1 ]]; then
  systemctl --user start "$SERVICE_NAME"
  echo "Service started: $SERVICE_NAME"
fi

echo "Tip: to start this service after reboot without interactive login, run:"
echo "  sudo loginctl enable-linger $USER"
