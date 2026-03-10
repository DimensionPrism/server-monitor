# Agentless Server Monitor Dashboard Design

**Date:** 2026-03-10  
**Status:** Approved

## Goal

Provide read-only monitoring for two (or more) cloud servers in one local browser tab without installing or cloning anything on remote servers.

## Scope

### In Scope

- Local-only dashboard service.
- SSH polling using existing local `~/.ssh/config` aliases.
- Local file settings store (`config/servers.toml`) editable from UI.
- CRUD for servers and working directories in UI.
- Per-server panel toggles for built-in panels:
  - System
  - GPU
  - Git
  - Clash

### Out of Scope

- Remote safe controls (restart services, on-demand actions).
- Automatic Clash UI tunnel orchestration.
- Multi-user auth and shared deployments.

## Architecture

### Local Dashboard Service

- FastAPI backend + WebSocket.
- Background runtime polls each configured server over SSH.
- No remote agent service and no public remote ports.

### SSH Data Collection

Per server alias:

- Fast loop (~3s): system + GPU commands.
- Slow loop (~10-15s): git status + Clash checks.

All commands execute as:

`ssh <alias> "<remote command>"`

### Settings Store

- File: `config/servers.toml`
- Stores:
  - server id
  - ssh alias
  - working directories
  - enabled panels
  - optional interval overrides

Writes are validated and atomic.

### Frontend

- Monitoring view renders server cards and only enabled panels.
- Settings view allows create/edit/delete:
  - server entries
  - working directories
  - panel toggles

## Data Flow

1. User edits settings in browser.
2. Backend validates and writes `config/servers.toml`.
3. Runtime reads updated settings and adjusts polling targets.
4. Parsed snapshots stream to browser via WebSocket.

## Error Handling

- Collector failures are isolated by source and server.
- Stale badges are shown when updates exceed thresholds.
- Partial snapshots remain visible when one source fails.
- SSH failures do not crash runtime loop.

## Security

- Reuses existing local SSH trust and key config.
- No password storage in app.
- No remote installation requirement.

## Testing Strategy

- Unit tests for settings load/save/validation.
- Unit tests for SSH command assembly and parser behavior.
- Runtime tests with mocked SSH executor.
- API tests for settings CRUD endpoints.
- UI smoke tests for settings and monitor rendering paths.

## Success Criteria

- User can monitor servers without cloning/installing code remotely.
- User can manage servers and working directories from browser UI.
- Panel toggles apply per server in live dashboard.
- Live data updates over WebSocket under normal SSH connectivity.

