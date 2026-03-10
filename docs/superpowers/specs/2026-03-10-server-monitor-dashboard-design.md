# Server Monitor Dashboard Design

**Date:** 2026-03-10  
**Status:** Approved

## Goal

Build a read-only, single-window dashboard (browser tab) that monitors two GPU cloud servers with near real-time updates for:

- system resources
- GPU resources
- git repository status for configured working directories
- Clash for Linux status
- quick links for SSH and tool access

Python package management must use `uv`.

## Scope

### In Scope (v1)

- Local dashboard backend + frontend on the user's machine
- One lightweight Python agent per server
- SSH-tunneled agent access only (no public agent ports)
- Near real-time updates:
  - metrics every 2-3 seconds
  - git + Clash every 10-15 seconds
- 2-5 repos per server via config file
- Read-only monitoring with clear stale/error states

### Out of Scope (v1)

- Remote command execution from dashboard
- Multi-user auth/RBAC
- Long-term historical storage
- Public internet exposure of agent endpoints

## Architecture

### 1) Per-server Agent (Python)

Runs on each server and exposes localhost-only read endpoints:

- `GET /health`
- `GET /snapshot`
- `GET /repos`
- `GET /clash`

Internal modules:

- `collector_metrics` (2-3s loop): parses command outputs for CPU/RAM/disk/net and GPU
- `collector_git_clash` (10-15s loop): parses git and Clash status
- `snapshot_store`: latest snapshots + timestamps + per-field error metadata
- `agent_api`: read-only HTTP responses

### 2) Local Dashboard App (Python)

Runs on local machine and coordinates both servers:

- `server_connections`: maintains SSH sessions/tunnels to both agents
- `poll_scheduler`: pulls endpoints through tunnels
- `normalize_layer`: maps both servers into one shared schema
- `ws_broadcaster`: pushes updates to browser clients via WebSocket

### 3) Browser Dashboard (single page)

One tab with modules:

- Server A/B system metrics cards
- GPU cards (utilization, VRAM, temp, process summary)
- Repo status table by server
- Clash status card
- quick links/instructions for SSH and Clash UI access

## Data Collection Strategy

User requested command-output parsing (instead of direct API libraries).

### System Metrics

Parse stable CLI outputs (Linux), e.g.:

- `top` / `vmstat` / `free`
- `df`
- network/device stats via standard commands

### GPU Metrics

Parse:

- `nvitop` output where feasible
- fallback/primary stable query via `nvidia-smi --query-* --format=csv,noheader,nounits`

### Git Status (per configured repo)

Per repo:

- `git rev-parse --abbrev-ref HEAD`
- `git status --porcelain`
- ahead/behind against upstream
- last commit age

### Clash Status

Checks include:

- process running
- expected local ports listening
- optional local health endpoint/proxy test
- dashboard provides access instructions/link metadata

## Security Model

- Agent binds to `127.0.0.1` only on each server
- Local app reads agent only through SSH tunnel
- No direct public inbound to agent
- Credentials via SSH keys and local config

## Configuration

### Local Config

Defines:

- both servers (host, port, user, ssh key path)
- tunnel local ports
- polling intervals
- per-server repo path lists

### Agent Config

Defines:

- repo directories
- command paths/overrides
- Clash check parameters

## Error Handling & Resilience

- Collectors isolated: failure in one source does not block others
- Every value carries timestamp/source/error fields
- Staleness thresholds drive warning badges in UI
- SSH reconnect with backoff on disconnect
- Partial data always shown; no hard-fail blank screen

## Testing Strategy

### Unit Tests

- Parser tests from captured real command outputs
- Normalization/schema tests
- staleness and status classification logic

### Integration Tests

- agent endpoint tests with mocked command runner
- local poller tests with fake SSH/tunnel layer
- reconnection and partial-failure flows

### Frontend Tests

- render for two-server state
- stale/error badges
- repo/Clash panel fallback handling

## Success Criteria

- Two servers visible in one dashboard tab
- Metrics update roughly every 2-3 seconds
- Git and Clash update every 10-15 seconds
- If one data source fails, remaining panels continue updating
- No public exposure required for server agents
- v1 runs locally using `uv` managed Python environment

