# Server Monitor Codex

Read-only local dashboard for monitoring two GPU cloud servers in one browser tab.

## Features (v1)

- Near real-time server metrics (2-3s)
- GPU usage snapshots
- Git status for configured repos (10-15s)
- Clash status checks
- Single dashboard UI with websocket updates

## Requirements

- Python 3.12+
- `uv` package manager
- SSH key-based access from local machine to both servers

## Setup

```bash
uv sync
```

## Run server agent on each remote server

1. Copy this project (or install package) on server.
2. Create config from `config/agent.example.toml`.
3. Start agent (bind localhost only):

```bash
SERVER_MONITOR_AGENT_CONFIG=config/agent.example.toml \
uv run uvicorn server_monitor.agent.main:build_app --factory --host 127.0.0.1 --port 9000
```

## Run local dashboard

1. Create local config from `config/local-dashboard.example.toml`.
2. Ensure SSH tunnels can reach each server agent port.
3. Start dashboard:

```bash
uv run uvicorn server_monitor.dashboard.main:build_dashboard_app --factory --host 127.0.0.1 --port 8080
```

4. Open `http://127.0.0.1:8080`.

## Testing

```bash
uv run pytest -q
uv run ruff check .
```
