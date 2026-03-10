# v1.1 Clash Reachability Checks Design (Agentless Runtime)

## Summary

Implement real Clash reachability checks in the dashboard's agentless runtime, replacing placeholder booleans:

- `api_reachable`
- `ui_reachable`

Checks must be secret-aware for both API and UI probes, using a read-only server command each status cycle to retrieve the secret.

## Scope

### In Scope

- Agentless dashboard runtime (`src/server_monitor/dashboard/runtime.py`) only
- Per-server configurable Clash probe URLs
- HTTP reachability check policy: **2xx only** for API and UI
- Per-status-cycle secret retrieval via remote read-only command
- Authenticated probes with `Authorization: Bearer <secret>` for API and UI
- Settings/API/UI updates required to configure probe URLs

### Out of Scope

- Agent-side collectors/config (`src/server_monitor/agent/*`)
- Clash UI tunnel-open flow (separate roadmap item)
- Notifications/retry architecture changes unrelated to Clash checks

## Requirements

1. Keep existing Clash payload shape compatible:
   - `running`, `api_reachable`, `ui_reachable`, `message`, `last_updated_at`
2. Probe URLs are configurable per server with defaults:
   - `clash_api_probe_url`: `http://127.0.0.1:9090/version`
   - `clash_ui_probe_url`: `http://127.0.0.1:9090/ui`
3. Runtime obtains secret each status cycle via read-only command:
   - default command: `clashsecret`
4. Both API and UI probes include Bearer auth header.
5. Reachability is true only when HTTP status is 2xx.

## Settings and API Design

Extend dashboard server settings model with optional fields:

- `clash_api_probe_url: str`
- `clash_ui_probe_url: str`

Persistence:

- Store/load fields in `DashboardSettingsStore`.
- Keep backward compatibility for existing TOML files by applying defaults when keys are missing.

API:

- Include fields in server create/update/read payloads (`dashboard/api.py` models).
- Preserve compatibility: clients omitting fields still succeed using defaults.

UI:

- Add settings form inputs for API/UI probe URLs in add/edit server forms.
- Include values in create/update requests.

## Runtime Design

### Secret Retrieval

Per status cycle and per server (when Clash panel enabled and status poll runs):

1. Run read-only secret command on remote host.
2. Parse secret from command output.
3. If missing/unparseable, mark Clash probes unreachable and set reason message.

Default command behavior assumptions:

- `clashsecret` outputs a line containing the current key (for example, `当前密钥：mysecret`).
- Non-zero exit or parse failure is handled as `secret-unavailable`.

### Clash Probe Command

Replace placeholder `_clash_command()` with a parameterized version:

`_clash_command(api_probe_url, ui_probe_url, secret)`

Command responsibilities:

- `running`: process check (`pgrep -f clash`)
- `api_reachable`: authenticated HTTP probe to API URL, true only on 2xx
- `ui_reachable`: authenticated HTTP probe to UI URL, true only on 2xx
- `message`: concise status reason for troubleshooting

Probe behavior:

- Use `curl` with short timeouts.
- Treat missing curl, command errors, non-2xx, and connection failures as unreachable.

### Message Codes

Use concise stable message values for operator visibility:

- `ok`
- `secret-unavailable`
- `secret-parse-failed`
- `curl-missing`
- `api-non-2xx`
- `ui-non-2xx`
- `probe-error`

### Runtime Integration

- Clash status polling remains within existing status poll flow.
- Existing cache fallback behavior is preserved on command failures.
- Existing freshness behavior remains intact (Clash freshness reflects polling outcomes).

## Parsing Design

Add secret parsing helper to runtime with conservative extraction:

Primary pattern:

- `当前密钥：<value>`

Fallback patterns (if needed):

- `secret: <value>`
- `current secret: <value>`

If none match, secret retrieval fails for this cycle.

## Error Handling

- Secret unavailable:
  - `api_reachable=false`
  - `ui_reachable=false`
  - `message=secret-unavailable` (or parse-specific code)
- Probe execution failure:
  - booleans false
  - message reflects failure class
- Clash command execution failure:
  - retain cached Clash state per current runtime behavior

## Testing Plan

### Runtime Tests (`tests/dashboard/test_runtime.py`)

- Command builder includes configured API/UI URLs.
- Secret extraction succeeds for expected output format.
- Secret extraction failure sets unreachable flags and message.
- API/UI 2xx produce true booleans.
- API/UI non-2xx produce false booleans and message.
- Auth header included in probe command for both API and UI.

### Settings Store Tests (`tests/dashboard/test_settings_store.py`)

- New Clash URL fields persist on save/load.
- Missing keys load with defaults.

### Settings API Tests (`tests/dashboard/test_settings_api.py`)

- GET includes Clash URL fields.
- POST/PUT accept and persist Clash URL fields.

### Static/UI Tests (`tests/dashboard/test_static_routes.py`)

- Settings page includes Clash API/UI probe URL controls.
- App JS includes payload wiring for those fields.

## Acceptance Criteria

1. Agentless runtime no longer emits placeholder Clash reachability booleans.
2. API/UI reachability reflect real authenticated HTTP probe results (2xx-only).
3. Secret is retrieved by remote read-only command each status cycle.
4. Probe URLs are configurable per server and backward compatible with defaults.
5. Dashboard test suite remains green after changes.
