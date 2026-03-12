# v1.2 Notifications and Diagnostics Export Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the remaining `v1.2` roadmap work by adding transition-only failure notifications and a user-facing diagnostics export action to the local dashboard.

**Architecture:** Keep diagnostics export browser-driven on top of the existing `GET /api/diagnostics` bundle, and keep transition-only notification logic in the browser using the existing `command_health` WebSocket payload. Persist only the global notification preferences in dashboard settings; do not add a new poller-side notification subsystem.

**Tech Stack:** Python 3.12+, FastAPI, existing dashboard settings/runtime APIs, vanilla JavaScript, CSS, pytest, ruff, browser Notifications API.

---

## File Structure

- Modify: `src/server_monitor/dashboard/settings.py`
  - Add global notification settings models plus TOML load/save support.
- Modify: `src/server_monitor/dashboard/api.py`
  - Serialize notification settings and add a focused API route for saving them.
- Modify: `src/server_monitor/dashboard/static/index.html`
  - Add monitor toolbar controls and a clearly global notifications settings card shell.
- Modify: `src/server_monitor/dashboard/static/app.js`
  - Add diagnostics export, notification permission handling, transition-only alert gating, and notification settings save flows.
- Modify: `src/server_monitor/dashboard/static/styles.css`
  - Add compact toolbar and global notifications card styling.
- Modify: `config/servers.example.toml`
  - Document the new top-level notifications block.
- Modify: `tests/dashboard/test_settings_store.py`
  - Cover notification settings defaults and round-trip persistence.
- Modify: `tests/dashboard/test_settings_api.py`
  - Cover notification settings serialization and update flows.
- Modify: `tests/dashboard/test_static_routes.py`
  - Assert the new toolbar and notification settings UI hooks exist.
- Modify: `tests/dashboard/test_static_app_behavior.py`
  - Cover diagnostics export, global notification settings rendering, and transition-only notification gating.
- Modify: `README.md`
  - Document notifications and diagnostics export at a high level.

## Chunk 1: Notification Settings Persistence and API

### Task 1: Add failing settings-store tests for global notification settings

**Files:**
- Modify: `tests/dashboard/test_settings_store.py`
- Modify: `src/server_monitor/dashboard/settings.py`

- [ ] **Step 1: Add failing defaults test**

Extend `tests/dashboard/test_settings_store.py` with:

```python
def test_settings_store_defaults_notification_settings(tmp_path: Path):
    from server_monitor.dashboard.settings import DashboardSettingsStore

    store = DashboardSettingsStore(tmp_path / "servers.toml")

    loaded = store.load()

    assert loaded.notifications.desktop_enabled is False
    assert loaded.notifications.webhook_enabled is False
    assert loaded.notifications.webhook_url == ""
```

- [ ] **Step 2: Add failing round-trip test**

Extend `tests/dashboard/test_settings_store.py` with:

```python
def test_settings_store_round_trips_notification_settings(tmp_path: Path):
    from server_monitor.dashboard.settings import DashboardSettings, DashboardSettingsStore, NotificationSettings

    store = DashboardSettingsStore(tmp_path / "servers.toml")
    store.save(
        DashboardSettings(
            notifications=NotificationSettings(
                desktop_enabled=True,
                webhook_enabled=True,
                webhook_url="https://hooks.example.test/server-monitor",
            )
        )
    )

    loaded = store.load()

    assert loaded.notifications.desktop_enabled is True
    assert loaded.notifications.webhook_enabled is True
    assert loaded.notifications.webhook_url == "https://hooks.example.test/server-monitor"
```

- [ ] **Step 3: Run settings-store tests to verify RED**

Run:

```bash
uv run pytest tests/dashboard/test_settings_store.py -q
```

Expected: FAIL because `DashboardSettings` does not yet include notification settings.

- [ ] **Step 4: Implement notification settings models and persistence**

Update `src/server_monitor/dashboard/settings.py`:

```python
@dataclass(slots=True)
class NotificationSettings:
    desktop_enabled: bool = False
    webhook_enabled: bool = False
    webhook_url: str = ""


@dataclass(slots=True)
class DashboardSettings:
    metrics_interval_seconds: float = 3.0
    status_interval_seconds: float = 12.0
    notifications: NotificationSettings = field(default_factory=NotificationSettings)
    servers: list[ServerSettings] = field(default_factory=list)
```

Load/save rules:

- load `[notifications]` from TOML if present
- default missing values safely
- persist `notifications` as a top-level TOML table
- keep existing server serialization unchanged

- [ ] **Step 5: Re-run settings-store tests**

Run:

```bash
uv run pytest tests/dashboard/test_settings_store.py -q
```

Expected: PASS.

### Task 2: Add failing API tests and implement notification settings routes

**Files:**
- Modify: `tests/dashboard/test_settings_api.py`
- Modify: `src/server_monitor/dashboard/api.py`

- [ ] **Step 1: Add failing API serialization test**

Extend `tests/dashboard/test_settings_api.py` with:

```python
def test_settings_api_returns_notification_settings(tmp_path):
    from server_monitor.dashboard.settings import DashboardSettings, DashboardSettingsStore, NotificationSettings

    store = DashboardSettingsStore(tmp_path / "servers.toml")
    store.save(
        DashboardSettings(
            notifications=NotificationSettings(
                desktop_enabled=True,
                webhook_enabled=True,
                webhook_url="https://hooks.example.test/server-monitor",
            )
        )
    )
    client = _make_client(tmp_path)

    response = client.get("/api/settings")

    assert response.status_code == 200
    body = response.json()
    assert body["notifications"]["desktop_enabled"] is True
    assert body["notifications"]["webhook_enabled"] is True
    assert body["notifications"]["webhook_url"] == "https://hooks.example.test/server-monitor"
```

- [ ] **Step 2: Add failing update-route test**

Add a focused API test:

```python
def test_settings_api_updates_notification_settings(tmp_path):
    client = _make_client(tmp_path)

    response = client.put(
        "/api/settings/notifications",
        json={
            "desktop_enabled": True,
            "webhook_enabled": True,
            "webhook_url": "https://hooks.example.test/server-monitor",
        },
    )

    assert response.status_code == 200
    body = client.get("/api/settings").json()
    assert body["notifications"]["desktop_enabled"] is True
    assert body["notifications"]["webhook_enabled"] is True
    assert body["notifications"]["webhook_url"] == "https://hooks.example.test/server-monitor"
```

- [ ] **Step 3: Run API tests to verify RED**

Run:

```bash
uv run pytest tests/dashboard/test_settings_api.py -k "notification_settings" -q
```

Expected: FAIL because the settings response lacks `notifications` and the update route does not exist.

- [ ] **Step 4: Implement API serialization and update route**

Update `src/server_monitor/dashboard/api.py`:

- add a `NotificationSettingsPayload` model
- include `notifications` in `_serialize_settings(...)`
- add:

```python
@app.put("/api/settings/notifications")
def update_notification_settings(payload: NotificationSettingsPayload) -> dict:
    store = _require_store(settings_store)
    settings = store.load()
    settings.notifications = NotificationSettings(
        desktop_enabled=payload.desktop_enabled,
        webhook_enabled=payload.webhook_enabled,
        webhook_url=payload.webhook_url,
    )
    store.save(settings)
    return _serialize_settings(store.load())
```

- [ ] **Step 5: Re-run API tests**

Run:

```bash
uv run pytest tests/dashboard/test_settings_api.py -k "notification_settings" -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tests/dashboard/test_settings_store.py tests/dashboard/test_settings_api.py src/server_monitor/dashboard/settings.py src/server_monitor/dashboard/api.py
git commit -m "feat: add notification settings to dashboard config"
```

## Chunk 2: Monitor Toolbar and Settings UI

### Task 3: Add failing static tests for the toolbar and global notifications card

**Files:**
- Modify: `tests/dashboard/test_static_routes.py`
- Modify: `tests/dashboard/test_static_app_behavior.py`
- Modify: `src/server_monitor/dashboard/static/index.html`
- Modify: `src/server_monitor/dashboard/static/app.js`
- Modify: `src/server_monitor/dashboard/static/styles.css`

- [ ] **Step 1: Add failing static route assertions**

Extend `tests/dashboard/test_static_routes.py` with assertions like:

```python
def test_root_serves_monitor_toolbar_and_notifications_card():
    ...
    assert "monitor-toolbar" in response.text
    assert "export-diagnostics-btn" in response.text
    assert "notification-permission-btn" in response.text
    assert "settings-notifications-card" in response.text
```

Also assert the JS and CSS include hooks such as:

- `saveNotificationSettings`
- `exportDiagnostics`
- `.monitor-toolbar`
- `.settings-notifications-card`

- [ ] **Step 2: Add failing app behavior tests for notifications settings rendering**

Extend `tests/dashboard/test_static_app_behavior.py` with a case like:

```python
def test_render_settings_includes_global_notification_controls():
    _run_app_js_test(
        """
        const shell = document.getElementById("settings-shell");

        __testExports.state.settings = {
          notifications: {
            desktop_enabled: true,
            webhook_enabled: false,
            webhook_url: "https://hooks.example.test/server-monitor",
          },
          servers: [],
        };

        __testExports.renderSettings();

        if (!shell.innerHTML.includes("Notification Settings")) {
          throw new Error("global notifications card missing");
        }
        if (!shell.innerHTML.includes("https://hooks.example.test/server-monitor")) {
          throw new Error("notification webhook url missing");
        }
        """
    )
```

- [ ] **Step 3: Add failing app behavior test for diagnostics export**

Add a JS behavior test like:

```python
def test_export_diagnostics_downloads_json_bundle():
    _run_app_js_test(
        """
        let fetchedUrl = "";
        let downloadedName = "";
        let createdBlobText = "";

        globalThis.__fetch = async (url) => {
          fetchedUrl = url;
          return {
            ok: true,
            status: 200,
            json: async () => ({ generated_at: "2026-03-11T15:20:00Z", servers: [] }),
            text: async () => "",
          };
        };
        globalThis.__blobCapture = (text) => { createdBlobText = text; };
        globalThis.__downloadCapture = (name) => { downloadedName = name; };

        await __testExports.exportDiagnostics();

        if (fetchedUrl !== "/api/diagnostics") {
          throw new Error(`unexpected diagnostics url: ${fetchedUrl}`);
        }
        if (!downloadedName.endsWith(".json")) {
          throw new Error(`unexpected download name: ${downloadedName}`);
        }
        if (!createdBlobText.includes("\\"servers\\"")) {
          throw new Error("diagnostics json was not prepared for download");
        }
        """
    )
```

- [ ] **Step 4: Run targeted static tests to verify RED**

Run:

```bash
uv run pytest tests/dashboard/test_static_routes.py -k "toolbar or notifications_card" -q
uv run pytest tests/dashboard/test_static_app_behavior.py -k "notification_controls or export_diagnostics" -q
```

Expected: FAIL because the toolbar, card, and export helper do not exist yet.

- [ ] **Step 5: Implement the monitor toolbar and global settings card shells**

Update `src/server_monitor/dashboard/static/index.html`:

- add a monitor toolbar section above `#monitor-grid`
- add buttons with ids:
  - `export-diagnostics-btn`
  - `notification-permission-btn`
- add a status region:
  - `monitor-toolbar-status`
- add a dedicated settings card container with id:
  - `settings-notifications-card`

Update `src/server_monitor/dashboard/static/styles.css`:

- add `.monitor-toolbar`
- add `.monitor-toolbar-actions`
- add `.monitor-toolbar-status`
- add `.settings-notifications-card`
- keep layout compact and responsive

- [ ] **Step 6: Implement notification settings rendering and diagnostics export helpers**

Update `src/server_monitor/dashboard/static/app.js` with helpers such as:

```javascript
function getNotificationSettings() {
  const notifications = state.settings && state.settings.notifications;
  return {
    desktop_enabled: Boolean(notifications && notifications.desktop_enabled),
    webhook_enabled: Boolean(notifications && notifications.webhook_enabled),
    webhook_url: notifications && typeof notifications.webhook_url === "string" ? notifications.webhook_url : "",
  };
}

async function saveNotificationSettings() {
  ...
}

async function exportDiagnostics() {
  ...
}
```

Implementation requirements:

- render a clearly global notifications card with desktop/webhook toggles and webhook URL
- save it through `PUT /api/settings/notifications`
- fetch `/api/diagnostics` and trigger a JSON file download
- update toolbar status text on success/failure
- expose `exportDiagnostics` for JS behavior tests

- [ ] **Step 7: Re-run targeted static tests**

Run:

```bash
uv run pytest tests/dashboard/test_static_routes.py -k "toolbar or notifications_card" -q
uv run pytest tests/dashboard/test_static_app_behavior.py -k "notification_controls or export_diagnostics" -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add tests/dashboard/test_static_routes.py tests/dashboard/test_static_app_behavior.py src/server_monitor/dashboard/static/index.html src/server_monitor/dashboard/static/app.js src/server_monitor/dashboard/static/styles.css
git commit -m "feat: add diagnostics export and notification settings ui"
```

## Chunk 3: Transition-Only Failure Notifications

### Task 4: Add failing JS behavior tests for transition-only notifications

**Files:**
- Modify: `tests/dashboard/test_static_app_behavior.py`
- Modify: `src/server_monitor/dashboard/static/app.js`

- [ ] **Step 1: Add failing desktop notification gating test**

Extend `tests/dashboard/test_static_app_behavior.py` with:

```python
def test_command_health_transition_notifies_only_once_until_recovery():
    _run_app_js_test(
        """
        const sent = [];
        globalThis.Notification = function(title, options) {
          sent.push({ title, body: options && options.body ? options.body : "" });
        };
        globalThis.Notification.permission = "granted";

        __testExports.state.settings = {
          notifications: {
            desktop_enabled: true,
            webhook_enabled: false,
            webhook_url: "",
          },
          servers: [],
        };

        __testExports.processNotificationTransitions(null, {
          server_id: "server-a",
          command_health: {
            git: { state: "failed", detail: "One or more repos failed", updated_at: "2026-03-11T15:20:00Z" },
          },
        });
        __testExports.processNotificationTransitions(null, {
          server_id: "server-a",
          command_health: {
            git: { state: "failed", detail: "One or more repos failed", updated_at: "2026-03-11T15:21:00Z" },
          },
        });
        __testExports.processNotificationTransitions(null, {
          server_id: "server-a",
          command_health: {
            git: { state: "healthy", detail: "All repos healthy", updated_at: "2026-03-11T15:22:00Z" },
          },
        });
        __testExports.processNotificationTransitions(null, {
          server_id: "server-a",
          command_health: {
            git: { state: "cooldown", detail: "One or more repos are cooling down", updated_at: "2026-03-11T15:23:00Z" },
          },
        });

        if (sent.length !== 2) {
          throw new Error(`expected 2 notifications, got ${sent.length}`);
        }
        """
    )
```

- [ ] **Step 2: Add failing webhook payload test**

Add:

```python
def test_command_health_transition_posts_webhook_payload():
    _run_app_js_test(
        """
        const webhookCalls = [];
        globalThis.Notification = undefined;
        globalThis.__fetch = async (url, options = {}) => {
          webhookCalls.push({ url, options });
          return {
            ok: true,
            status: 200,
            json: async () => ({}),
            text: async () => "",
          };
        };

        __testExports.state.settings = {
          notifications: {
            desktop_enabled: false,
            webhook_enabled: true,
            webhook_url: "https://hooks.example.test/server-monitor",
          },
          servers: [],
        };

        await __testExports.processNotificationTransitions(null, {
          server_id: "server-a",
          command_health: {
            clash: { state: "cooldown", detail: "Command cooling down after repeated failures", updated_at: "2026-03-11T15:20:00Z" },
          },
        });

        if (webhookCalls.length !== 1) {
          throw new Error(`expected 1 webhook call, got ${webhookCalls.length}`);
        }
        if (webhookCalls[0].url !== "https://hooks.example.test/server-monitor") {
          throw new Error("webhook url mismatch");
        }
        if (!String(webhookCalls[0].options.body).includes("\\"panel\\":\\"clash\\"")) {
          throw new Error("webhook payload missing panel");
        }
        """
    )
```

- [ ] **Step 3: Run targeted JS behavior tests to verify RED**

Run:

```bash
uv run pytest tests/dashboard/test_static_app_behavior.py -k "notifies_only_once_until_recovery or webhook_payload" -q
```

Expected: FAIL because the transition processor does not exist.

- [ ] **Step 4: Implement transition-only notification processing**

Update `src/server_monitor/dashboard/static/app.js`:

- add state maps:
  - `notificationLatches`
- add helpers:

```javascript
function notificationKey(serverId, panelName) {
  return `${serverId}::${panelName}`;
}

function isDegradedCommandHealthState(state) {
  return state === "failed" || state === "cooldown";
}

async function deliverDesktopNotification(serverId, panelName, summary) {
  ...
}

async function deliverWebhookNotification(serverId, panelName, summary) {
  ...
}

async function processNotificationTransitions(previousUpdate, nextUpdate) {
  ...
}
```

Processing rules:

- only `failed` and `cooldown` notify
- repeated degraded updates do not notify again while the latch remains set
- `healthy` and `unknown` clear the latch
- `retrying` does not notify and does not clear a degraded latch
- use current `state.settings.notifications`
- keep failures local to status text; do not throw

Wire it into `connectWs()` before `renderMonitor()`:

```javascript
const previous = state.updates.get(payload.server_id) || null;
await processNotificationTransitions(previous, payload);
state.updates.set(payload.server_id, payload);
renderMonitor();
```

- [ ] **Step 5: Re-run targeted JS behavior tests**

Run:

```bash
uv run pytest tests/dashboard/test_static_app_behavior.py -k "notifies_only_once_until_recovery or webhook_payload" -q
```

Expected: PASS.

## Chunk 4: Documentation and Full Verification

### Task 5: Update docs, example config, and run verification

**Files:**
- Modify: `README.md`
- Modify: `config/servers.example.toml`
- Modify: `tests/dashboard/test_settings_store.py`
- Modify: `tests/dashboard/test_settings_api.py`
- Modify: `tests/dashboard/test_static_routes.py`
- Modify: `tests/dashboard/test_static_app_behavior.py`
- Modify: `src/server_monitor/dashboard/settings.py`
- Modify: `src/server_monitor/dashboard/api.py`
- Modify: `src/server_monitor/dashboard/static/index.html`
- Modify: `src/server_monitor/dashboard/static/app.js`
- Modify: `src/server_monitor/dashboard/static/styles.css`

- [ ] **Step 1: Update user-facing docs**

Add:

- a `README.md` bullet in "What Works Now" for transition-only desktop/webhook failure notifications
- a `README.md` bullet for in-dashboard diagnostics export
- a top-level `[notifications]` example in `config/servers.example.toml`

- [ ] **Step 2: Run focused dashboard verification**

Run:

```bash
uv run pytest tests/dashboard/test_settings_store.py tests/dashboard/test_settings_api.py tests/dashboard/test_static_routes.py tests/dashboard/test_static_app_behavior.py tests/dashboard/test_diagnostics_api.py -q
```

Expected: PASS.

- [ ] **Step 3: Run full verification**

Run:

```bash
uv run pytest -q
uv run ruff check .
```

Expected:

- pytest passes
- ruff reports no issues

- [ ] **Step 4: Commit**

```bash
git add README.md config/servers.example.toml tests/dashboard/test_settings_store.py tests/dashboard/test_settings_api.py tests/dashboard/test_static_routes.py tests/dashboard/test_static_app_behavior.py src/server_monitor/dashboard/settings.py src/server_monitor/dashboard/api.py src/server_monitor/dashboard/static/index.html src/server_monitor/dashboard/static/app.js src/server_monitor/dashboard/static/styles.css
git commit -m "feat: finish v12 notifications and diagnostics export"
```

Plan complete and saved to `docs/superpowers/plans/2026-03-11-v12-notifications-diagnostics-export.md`. Proceed with execution in this worktree using TDD.
