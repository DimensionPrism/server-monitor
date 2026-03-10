# Server Monitor Codex

Read-only local dashboard for monitoring two GPU cloud servers in one browser tab.

## Features (v1)

- Near real-time server metrics (2-3s)
- GPU usage snapshots
- Git status for configured repos (10-15s)
- Clash status checks
- Single dashboard UI with websocket updates
- Agent runs background collectors automatically at startup

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
2. Create config from `config/agent.example.toml` (defaults assume Linux tools: `bash`, `top`, `free`, `df`, `nvidia-smi`, `git`).
3. Start agent (bind localhost only):

```bash
SERVER_MONITOR_AGENT_CONFIG=config/agent.example.toml \
uv run uvicorn server_monitor.agent.main:build_app --factory --host 127.0.0.1 --port 9000
```

4. Verify from the server:

```bash
curl http://127.0.0.1:9000/health
curl http://127.0.0.1:9000/snapshot
```

## Run local dashboard

1. Create local config from `config/local-dashboard.example.toml`.
2. Ensure SSH tunnels can reach each server agent port. Example:

```bash
ssh -N -L 19001:127.0.0.1:9000 user@server-a
ssh -N -L 19002:127.0.0.1:9000 user@server-b
```

3. Save as `config/local-dashboard.toml`.
4. Start dashboard:

```bash
uv run uvicorn server_monitor.dashboard.main:build_dashboard_app --factory --host 127.0.0.1 --port 8080
```

5. Open `http://127.0.0.1:8080`.

## Testing

```bash
uv run pytest -q
uv run ruff check .
```
