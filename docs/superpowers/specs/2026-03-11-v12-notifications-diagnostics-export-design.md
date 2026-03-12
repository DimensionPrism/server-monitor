# v1.2 Notifications and Diagnostics Export Design

## Summary

The remaining `v1.2` roadmap work is operational visibility at the edge of the existing reliability work:

- lightweight failure notifications
- a user-facing diagnostics export action

The backend already exposes a redaction-safe diagnostics bundle at `GET /api/diagnostics`, and the runtime already publishes compact per-panel command health over WebSocket. That means the missing work is mostly product integration rather than another poller subsystem.

This slice should add:

- a small monitor toolbar action that exports the diagnostics bundle as a downloadable JSON file
- transition-only failure notifications driven by the existing `command_health` payload
- a global notifications settings card so operators can enable desktop notifications and optionally configure a webhook URL

The implementation should stay lightweight and local-first:

- keep the diagnostics export backend unchanged unless a test reveals a small gap
- keep notification transition tracking in browser memory
- avoid turning `v1.2` into a persistent alerting or incident-management system

## Scope

### In Scope

- Monitor toolbar UI for diagnostics export and notification status
- Browser-triggered diagnostics JSON download built on `GET /api/diagnostics`
- Transition-only failure notifications for degraded panel states
- Desktop/browser notifications when permission is granted
- Optional direct webhook POST delivery from the browser
- Global notification settings persistence and API serialization
- Frontend and settings/API tests covering the new behavior
- README updates describing the completed `v1.2` features

### Out of Scope

- Poller-side notification delivery
- Persistent notification history or acknowledgements
- Retry queues or durable webhook delivery
- Background notifications without an open dashboard tab
- Incident workflow integration
- Historical diagnostics archives on disk
- Additional diagnostics payload redesign

## Requirements

1. The diagnostics export action must be visible from the monitor view without opening developer tools or calling endpoints manually.
2. Diagnostics export must download the existing redaction-safe bundle as a JSON file with a timestamped filename.
3. Notification delivery must be transition-only:
   - notify when a panel enters `failed` or `cooldown`
   - do not re-notify while that panel remains degraded
   - allow later notifications after the panel recovers
4. `retrying` must remain visible in-card but must not trigger notifications.
5. Notification evaluation must reuse the existing WebSocket `command_health` payload rather than polling diagnostics.
6. Desktop notifications must only fire when:
   - the user has enabled the desktop toggle
   - browser permission is `granted`
7. Webhook notifications must only fire when:
   - the user has enabled the webhook toggle
   - a non-empty webhook URL is configured
8. Notification failures must not block monitor rendering, WebSocket handling, or diagnostics export.
9. Notification configuration must be stored as global dashboard settings, not duplicated per server.
10. The first version may keep webhook delivery as direct browser `fetch`; CORS or remote endpoint constraints are acceptable documented limitations for `v1.2`.

## Proposed Module Boundaries

### `src/server_monitor/dashboard/settings.py`

Extend the settings model with global notification configuration.

Responsibilities:

- define the notification settings shape
- load notification defaults from TOML
- persist notification settings back to TOML

### `src/server_monitor/dashboard/api.py`

Expose notification settings through the existing settings API.

Responsibilities:

- serialize global notification settings in `GET /api/settings`
- accept notification settings on create and update flows where appropriate
- keep `GET /api/diagnostics` unchanged unless tests require a minor compatibility adjustment

### `src/server_monitor/dashboard/static/index.html`

Add compact global UI affordances.

Responsibilities:

- render a monitor toolbar above the server grid
- provide diagnostics export and notification permission controls
- provide a compact status line for local success and failure messages

### `src/server_monitor/dashboard/static/app.js`

Own browser-side notifications and diagnostics export.

Responsibilities:

- fetch and download diagnostics bundles
- request and reflect browser notification permission
- compare previous vs current `command_health` states per server and panel
- send desktop notifications and optional webhook POSTs on eligible transitions
- keep dedupe state in browser memory

### `src/server_monitor/dashboard/static/styles.css`

Add compact styling for the toolbar and notifications settings card.

Responsibilities:

- fit the toolbar into the current monitor layout without overshadowing cards
- preserve mobile wrapping behavior
- style notification controls consistently with the existing settings workspace

## Settings Design

Add a global notifications block to dashboard settings.

Suggested Python shape:

```python
@dataclass(slots=True)
class NotificationSettings:
    desktop_enabled: bool = False
    webhook_enabled: bool = False
    webhook_url: str = ""
```

Suggested `DashboardSettings` addition:

```python
notifications: NotificationSettings = field(default_factory=NotificationSettings)
```

Suggested API/settings JSON shape:

```json
{
  "metrics_interval_seconds": 3.0,
  "status_interval_seconds": 12.0,
  "notifications": {
    "desktop_enabled": false,
    "webhook_enabled": false,
    "webhook_url": ""
  },
  "servers": []
}
```

Suggested TOML shape:

```toml
metrics_interval_seconds = 3
status_interval_seconds = 12

[notifications]
desktop_enabled = false
webhook_enabled = false
webhook_url = ""
```

This should remain global because the notification destination is an operator preference, not a server identity attribute.

## Diagnostics Export Design

### User Flow

1. Operator clicks `Export Diagnostics` in the monitor toolbar.
2. Browser performs `GET /api/diagnostics`.
3. Browser serializes the response with stable indentation and triggers a file download.
4. Toolbar status text updates with success or failure.

### Filename Format

Use a timestamped filename such as:

- `server-monitor-diagnostics-2026-03-11-231500.json`

Local browser time is acceptable for the filename because the bundle itself already includes `generated_at`.

### Download Behavior

- Use a `Blob` and temporary object URL.
- Avoid opening a new page or raw JSON tab.
- Revoke the object URL after download is triggered.

### Failure Handling

- If the fetch fails, show a concise toolbar status such as `Export failed: 503 diagnostics unavailable`.
- Do not retry automatically.
- Do not block live monitor updates.

## Notification Design

### Eligible States

Notification-worthy degraded states:

- `failed`
- `cooldown`

Non-notifying states:

- `healthy`
- `unknown`
- `retrying`

### Transition Rules

Track one in-memory latch per `(server_id, panel_name)`.

Rules:

1. If the previous visible state was `healthy`, `unknown`, or absent and the new state is `failed` or `cooldown`, notify and set the latch.
2. If the new state remains `failed` or `cooldown` and the latch is set, do not notify again.
3. If the new state becomes `healthy` or `unknown`, clear the latch.
4. If the new state becomes `retrying`, do not notify and do not clear a degraded latch unless the prior degraded state has already resolved through `healthy` or `unknown`.

This keeps the behavior intentionally conservative and avoids duplicate alerts during repeated failed polls.

### Desktop Notification Content

Use short, readable notification text based on panel detail already present in `command_health`.

Suggested title:

- `Server Monitor: server-a`

Suggested body:

- `CLASH entered cooldown`
- `GIT failed: One or more repos failed`

Body content must remain UI-safe and must not expose secrets.

### Webhook Payload

Send a small JSON payload from the browser:

```json
{
  "source": "server-monitor-dashboard",
  "server_id": "server-a",
  "panel": "clash",
  "state": "cooldown",
  "detail": "Command cooling down after repeated failures",
  "timestamp": "2026-03-11T15:20:00Z"
}
```

Guidelines:

- use `POST`
- send `Content-Type: application/json`
- do not attach the full diagnostics bundle
- do not retry or batch in `v1.2`

### Browser Permission Handling

The monitor toolbar should expose a notification button whose label reflects current permission state:

- `Enable Notifications` when desktop notifications are enabled in settings but permission is not granted
- `Notifications On` when enabled and permission is granted
- `Desktop Off` when the desktop toggle is disabled

Request browser permission only on explicit user action. Do not auto-prompt on page load.

## UI Rendering Rules

### Monitor Toolbar

Render a slim toolbar above the server board containing:

- `Export Diagnostics` button
- notification permission/status button
- muted status text region

The toolbar should:

- stay compact
- wrap on narrow screens
- visually read as dashboard controls, not another content card

### Settings Workspace

Add a dedicated global notifications card near the top of the settings editor area or in a clearly global section outside the per-server editor.

Fields:

- desktop notifications enabled
- webhook notifications enabled
- webhook URL

The card should be clearly labeled as global so it is not mistaken for server-specific configuration.

## Error Handling

### Diagnostics Export

- Show local toolbar status on export failure.
- Keep the existing diagnostics backend response as the source of truth.
- If diagnostics support is unavailable, the UI should fail gracefully rather than hiding the button.

### Desktop Notifications

- If permission is denied, update local status text and do not retry automatically.
- If the browser does not support `Notification`, degrade gracefully and surface a short message.

### Webhook Notifications

- If the POST fails, update local status text with a concise error.
- Do not mark the degraded transition as unresolved just because webhook delivery failed.
- Do not block desktop notification delivery if the webhook fails.

## Testing Strategy

### Settings and API Tests

Add or extend tests for:

- default notification settings in empty settings files
- settings round-trip for the global notifications block
- settings API serialization of the notifications object
- create and update flows preserving notification settings when servers change

### Static Route Tests

Add tests that assert:

- monitor toolbar markup exists in the root page
- notification settings controls exist in static HTML or JS hooks
- app JS contains the export and notification control logic hooks

### Frontend Behavior Tests

Add behavior tests for:

- diagnostics export fetches `/api/diagnostics` and creates a download
- transition into `failed` triggers one notification
- repeated `failed` updates do not re-notify
- recovery clears the latch
- later degradation re-notifies
- webhook payload shape for degraded transitions
- toolbar status updates on permission or delivery failures

### Regression Coverage

Keep existing monitor rendering and settings editing behavior intact:

- command health strip still renders as before
- server settings editing still preserves drafts
- existing diagnostics endpoint tests remain green

## Acceptance Criteria

1. The monitor view exposes an `Export Diagnostics` action that downloads the diagnostics bundle as JSON.
2. Operators can enable desktop notifications and optionally configure a webhook URL in global settings.
3. Desktop and webhook notifications fire only when a panel transitions into `failed` or `cooldown`.
4. Repeated degraded updates do not create duplicate notifications until recovery occurs.
5. `retrying` remains visible in-card and does not trigger notifications.
6. Notification failures do not break live monitoring or diagnostics export.
7. Dashboard tests remain green after the change.
