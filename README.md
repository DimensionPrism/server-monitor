# Server Monitor Codex (Agentless)

Local dashboard for monitoring remote GPU servers over SSH aliases in a single browser tab.

## What Works Now

- Agentless monitoring (no remote repo clone/install needed)
- Summary-first server cards with a metrics-only collapsed state for faster daily scanning
- Agentless continuous SSH streaming for `system` and `gpu`
- Snapshot polling over SSH for `git` and `clash`
- Freshness badges (`LIVE`/`CACHED`) for System/GPU/Git/Clash panels and repo rows
- Multi-GPU summary signal on each card (`active/total` devices plus `peak` utilization)
- Secret-aware Clash API/UI reachability checks with configurable probe URLs
- One-click Clash UI tunnel-open action from the Clash panel
- Batched SSH polling for the live dashboard shape:
  - one transport round trip for `system` + `gpu`
  - one transport round trip for combined `git` + `clash`
- Persistent per-alias SSH shell reuse for batched polls, with automatic fallback to one-shot SSH when the session breaks
- Clash UI login assist from dashboard:
  - auto-construct setup/login URL after tunnel open
  - copy Clash secret from card (`Copy Secret`)
  - secret probe fallback (`clashsecret` -> `clashctl secret` -> `runtime.yaml`)
- Policy-driven polling retries with short cooldowns for repeated command failures
- Per-card command health strip with latency-first healthy state and retry/cooldown/failure summaries
- Exportable diagnostics bundle at `GET /api/diagnostics`
- In-dashboard `Export Diagnostics` action for downloading the diagnostics bundle as JSON
- Transition-only failure notifications from the dashboard:
  - desktop/browser notifications when enabled and permission is granted
  - optional webhook POST on new `failed` or `cooldown` panel transitions
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
- Background logs: `logs\dashboard.log` and `logs\dashboard.stderr.log`.

## Notes

- Runtime loads `config/servers.toml` by default.
- Override settings path with:
  - `SERVER_MONITOR_SETTINGS_PATH=/path/to/servers.toml`
- You can also manage most settings directly from the browser Settings tab with add/reopen, overview, and focused edit flows.
- `system` and `gpu` now use one long-lived SSH metrics stream per configured server.
- The first streaming version targets roughly `4/sec` internally and does not expose a separate stream-rate setting in the settings file or UI.
- `metrics_interval_seconds` still controls the runtime loop cadence for background status work; it no longer controls `system`/`gpu` sample frequency when streaming is enabled.
- Git operations are restricted to repo paths declared in each server's `working_dirs`.
- No destructive git commands are exposed in the UI/API.
- Clash panel can open/reuse a local SSH forward and launch the remote Clash UI in a browser tab.
- Clash tunnel-open now returns secret/login context; UI will auto-open setup URL when available and try to copy secret to clipboard.
- Status polling now runs on a non-blocking background path so stalled SSH status commands no longer block dashboard cycles or overwrite the last good Clash snapshot on transient secret command failures.
- Batched polling keeps card detail and freshness the same while lowering SSH setup overhead on the default dashboard card mix.
- Batched polls prefer a persistent SSH shell per alias and automatically retry through the existing one-shot SSH path if the persistent transport fails.
- If a metrics stream drops, the last good `system`/`gpu` sample stays visible while freshness ages from `LIVE` to `CACHED`, and the command-health chips switch to stream-state labels like `reconnecting`.
- Clash reachability treats HTTP redirects (`3xx`) as reachable to support `/ui` -> `/ui/` style responses.
- Recent command health is kept in memory so repeated transient failures can retry in a bounded way and briefly cool down before the next attempt.
- `GET /api/diagnostics` returns a redaction-safe JSON bundle of current settings and recent command outcomes for debugging/sharing.
- `GET /api/diagnostics` now also exposes per-server `metrics_stream` state, last sample metadata, and reconnect counters.
- The monitor toolbar can export the diagnostics bundle directly as a timestamped JSON download.
- A quick latency check after launch:
  - start the dashboard
  - open `GET /api/diagnostics`
  - compare the `metrics_stream` section for `system`/`gpu` liveliness and the latest `duration_ms` values for `git_status`, `clash_secret`, and `clash_probe`
- Failure notifications are evaluated in the open browser session from live `command_health` updates and only fire on new degraded transitions.

## Testing

```bash
uv run pytest -q
uv run ruff check .
```
