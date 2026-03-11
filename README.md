# Server Monitor Codex (Agentless)

Local dashboard for monitoring remote GPU servers over SSH aliases in a single browser tab.

## What Works Now

- Agentless monitoring (no remote repo clone/install needed)
- Summary-first server cards with a metrics-only collapsed state for faster daily scanning
- System/GPU/Git/Clash snapshot polling over SSH
- Freshness badges (`LIVE`/`CACHED`) for System/GPU/Git/Clash panels and repo rows
- Multi-GPU summary signal on each card (`active/total` devices plus `peak` utilization)
- Secret-aware Clash API/UI reachability checks with configurable probe URLs
- One-click Clash UI tunnel-open action from the Clash panel
- Clash UI login assist from dashboard:
  - auto-construct setup/login URL after tunnel open
  - copy Clash secret from card (`Copy Secret`)
  - secret probe fallback (`clashsecret` -> `clashctl secret` -> `runtime.yaml`)
- Policy-driven polling retries with short cooldowns for repeated command failures
- Exportable diagnostics bundle at `GET /api/diagnostics`
- Live WebSocket updates in dashboard
- Git safe operations from dashboard Git panel:
  - `refresh`
  - `fetch --prune --tags`
  - `pull --ff-only`
  - `checkout <branch>` (validated branch names only)
- Git repo card action:
  - `Open in Terminal` (opens a local terminal into the selected remote repo via SSH)
- Interactive settings UI:
  - premium split settings workspace with overview-first navigation
  - `Add Server` form expands for first-run setup, then collapses behind an `Add Server` button once servers exist
  - create/edit/delete servers
  - create/edit/delete working directories
  - focused single-server editor with grouped cards and draft preservation while switching rows
  - sticky action footer with stronger `Save`/`Delete` hierarchy
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
- You can also manage most settings directly from the browser Settings tab with add/reopen, overview, and focused edit flows.
- Git operations are restricted to repo paths declared in each server's `working_dirs`.
- No destructive git commands are exposed in the UI/API.
- Clash panel can open/reuse a local SSH forward and launch the remote Clash UI in a browser tab.
- Clash tunnel-open now returns secret/login context; UI will auto-open setup URL when available and try to copy secret to clipboard.
- Status polling now runs on a non-blocking background path so stalled SSH status commands no longer block dashboard cycles or overwrite the last good Clash snapshot on transient secret command failures.
- Clash reachability treats HTTP redirects (`3xx`) as reachable to support `/ui` -> `/ui/` style responses.
- Recent command health is kept in memory so repeated transient failures can retry in a bounded way and briefly cool down before the next attempt.
- `GET /api/diagnostics` returns a redaction-safe JSON bundle of current settings and recent command outcomes for debugging/sharing.

## Testing

```bash
uv run pytest -q
uv run ruff check .
```
