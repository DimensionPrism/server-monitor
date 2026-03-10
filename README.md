# Server Monitor Codex (Agentless)

Local dashboard for monitoring remote GPU servers over SSH aliases in a single browser tab.

## What Works Now

- Agentless monitoring (no remote repo clone/install needed)
- System/GPU/Git/Clash snapshot polling over SSH
- Live WebSocket updates in dashboard
- Interactive settings UI:
  - create/edit/delete servers
  - create/edit/delete working directories
  - toggle built-in panels per server (`system`, `gpu`, `git`, `clash`)

## Requirements

- Python 3.12+
- `uv`
- Local SSH access to remote servers
- SSH aliases configured in local `~/.ssh/config`
- Remote tools available on servers:
  - `bash`, `top`, `free`, `df`
  - `nvidia-smi` (for GPU panel)
  - `git` (for git panel)
  - `pgrep` (for clash process check)

## Setup

```bash
uv sync
```

Copy settings template:

```bash
cp config/servers.example.toml config/servers.toml
```

Edit `config/servers.toml` with your SSH aliases and repo paths.

## Run

```bash
uv run uvicorn server_monitor.dashboard.main:build_dashboard_app --factory --host 127.0.0.1 --port 8080
```

Open:

- `http://127.0.0.1:8080`

## Notes

- Runtime loads `config/servers.toml` by default.
- Override settings path with:
  - `SERVER_MONITOR_SETTINGS_PATH=/path/to/servers.toml`
- You can also manage most settings directly from the browser Settings tab.

## Testing

```bash
uv run pytest -q
uv run ruff check .
```

