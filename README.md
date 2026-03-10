# Server Monitor Codex (Agentless)

Local dashboard for monitoring remote GPU servers over SSH aliases in a single browser tab.

## What Works Now

- Agentless monitoring (no remote repo clone/install needed)
- System/GPU/Git/Clash snapshot polling over SSH
- Freshness badges (`LIVE`/`CACHED`) for System/GPU/Git/Clash panels and repo rows
- Secret-aware Clash API/UI reachability checks with configurable probe URLs
- Live WebSocket updates in dashboard
- Git safe operations from dashboard Git panel:
  - `refresh`
  - `fetch --prune --tags`
  - `pull --ff-only`
  - `checkout <branch>` (validated branch names only)
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

## Windows Background Scripts

Use these from PowerShell in the repo root:

```powershell
.\scripts\start-dashboard.ps1
.\scripts\stop-dashboard.ps1
.\scripts\install-dashboard-task.ps1 -TaskName ServerMonitorDashboard -Port 8080 -StartNow
```

Notes:

- `start-dashboard.ps1` runs in background by default.
- Use `-Foreground` for interactive logs.
- Background logs: `logs\dashboard.log`.

## Notes

- Runtime loads `config/servers.toml` by default.
- Override settings path with:
  - `SERVER_MONITOR_SETTINGS_PATH=/path/to/servers.toml`
- You can also manage most settings directly from the browser Settings tab.
- Git operations are restricted to repo paths declared in each server's `working_dirs`.
- No destructive git commands are exposed in the UI/API.
- The planned one-click Clash UI tunnel-open flow is not implemented yet.
- Status polling now runs on a non-blocking background path so stalled SSH status commands no longer block dashboard cycles or overwrite the last good Clash snapshot on transient secret command failures.

## Testing

```bash
uv run pytest -q
uv run ruff check .
```
