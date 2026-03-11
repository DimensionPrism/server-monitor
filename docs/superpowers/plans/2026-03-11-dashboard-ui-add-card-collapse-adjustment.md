# Dashboard UI Add Card Collapse Adjustment Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adjust the premium settings workspace so the add-server card is first-run/open, then collapses into a compact reopen flow after servers exist.

**Architecture:** Keep the current premium split settings workspace and add a small piece of client-side UI state to control whether the add card is expanded. Drive the default from server count, collapse immediately after successful add, and reset the form whenever the card is collapsed.

**Tech Stack:** FastAPI static frontend, vanilla JavaScript, CSS, pytest, ruff, uv.

---

## File Map

- `src/server_monitor/dashboard/static/index.html`
  - Add the dedicated `Add Server` reopen button and any minimal shell hooks for the collapsed card state.
- `src/server_monitor/dashboard/static/app.js`
  - Track add-card expansion state, derive defaults from server count, collapse after successful add, and reset the add form on collapse.
- `src/server_monitor/dashboard/static/styles.css`
  - Style the add-card collapsed state and reopen button.
- `tests/dashboard/test_static_routes.py`
  - Assert the new add-card shell hooks.
- `tests/dashboard/test_static_app_behavior.py`
  - Cover add-card state defaults, auto-collapse, and reset behavior.

## Chunk 1: Lock the Add Card Behavior with Tests

### Task 1: Add failing static and behavior coverage for the add-card flow

**Files:**
- Modify: `tests/dashboard/test_static_routes.py`
- Modify: `tests/dashboard/test_static_app_behavior.py`
- Test: `tests/dashboard/test_static_routes.py`
- Test: `tests/dashboard/test_static_app_behavior.py`

- [ ] **Step 1: Add a failing static test for the reopen-button and add-card hooks**

```python
def test_root_serves_add_server_toggle_hooks():
    response = client.get("/")
    assert "settings-add-toggle" in response.text
    assert "settings-add-card" in response.text
```

- [ ] **Step 2: Run the targeted static test to verify it fails**

Run: `uv run pytest tests/dashboard/test_static_routes.py::test_root_serves_add_server_toggle_hooks -q`
Expected: FAIL because the new hooks do not exist yet.

- [ ] **Step 3: Add failing Node-backed behavior tests for the add-card state**

```python
def test_add_server_card_defaults_open_only_when_no_servers():
    result = node_static_app("render empty settings, then populated settings, and read the add-card state markers")
    assert result["emptyState"] == "open"
    assert result["existingState"] == "collapsed"

def test_add_server_card_collapses_and_resets_after_add():
    result = node_static_app("submit the add form, collapse the card, and read the reset field values")
    assert result["collapsedAfterAdd"] is True
    assert result["serverIdAfterCollapse"] == ""
```

- [ ] **Step 4: Run the targeted behavior tests and keep them red**

Run: `uv run pytest tests/dashboard/test_static_app_behavior.py -k "add_server_card_defaults_open_only_when_no_servers or add_server_card_collapses_and_resets_after_add" -q`
Expected: FAIL.

- [ ] **Step 5: Commit the failing tests**

```bash
git add tests/dashboard/test_static_routes.py tests/dashboard/test_static_app_behavior.py
git commit -m "test: require add server collapse flow"
```

## Chunk 2: Implement the Add Card Collapse Flow

### Task 2: Implement add-card state, collapse, reset, and styling

**Files:**
- Modify: `src/server_monitor/dashboard/static/index.html`
- Modify: `src/server_monitor/dashboard/static/app.js`
- Modify: `src/server_monitor/dashboard/static/styles.css`
- Test: `tests/dashboard/test_static_routes.py`
- Test: `tests/dashboard/test_static_app_behavior.py`

- [ ] **Step 1: Add the dedicated reopen button and shell hooks in `index.html`**

```html
<div class="settings-shell-head">
  <button id="settings-add-toggle" class="settings-add-toggle" type="button">Add Server</button>
</div>
<div id="settings-add-card" class="settings-add-card"></div>
```

- [ ] **Step 2: Add client-side state and reset helpers in `app.js`**

```javascript
state.settingsAddExpanded = true;

function resetAddServerForm() {
  byId("new-server-id").value = "";
  byId("new-server-alias").value = "";
  byId("new-server-dirs").value = "";
  byId("new-clash-api-probe-url").value = DEFAULT_CLASH_API_PROBE_URL;
  byId("new-clash-ui-probe-url").value = DEFAULT_CLASH_UI_PROBE_URL;
}

function setSettingsAddExpanded(expanded, options = {}) {
  state.settingsAddExpanded = expanded;
  if (!expanded && options.reset) {
    resetAddServerForm();
  }
  renderSettingsAddCard();
}
```

- [ ] **Step 3: Derive default expansion from server count and collapse immediately after successful add**

```javascript
const hasServers = servers.length > 0;
if (!state.settingsAddTouched) {
  state.settingsAddExpanded = !hasServers;
}
await api("POST", "/api/servers", payload);
setSettingsAddExpanded(false, { reset: true });
```

- [ ] **Step 4: Add the collapsed-state styling**

```css
.settings-add-toggle { justify-self: start; }
.settings-add-card.collapsed { max-height: 0; opacity: 0; overflow: hidden; }
.settings-shell[data-add-expanded="false"] .settings-add-card { padding: 0; border-width: 0; }
```

- [ ] **Step 5: Run the targeted tests and verify they pass**

Run: `uv run pytest tests/dashboard/test_static_routes.py::test_root_serves_add_server_toggle_hooks -q`
Expected: PASS.

Run: `uv run pytest tests/dashboard/test_static_app_behavior.py -k "add_server_card_defaults_open_only_when_no_servers or add_server_card_collapses_and_resets_after_add" -q`
Expected: PASS.

- [ ] **Step 6: Run full verification**

Run: `uv run ruff check .`
Expected: PASS.

Run: `uv run pytest -q`
Expected: PASS.

- [ ] **Step 7: Commit the implementation**

```bash
git add src/server_monitor/dashboard/static/index.html src/server_monitor/dashboard/static/app.js src/server_monitor/dashboard/static/styles.css tests/dashboard/test_static_routes.py tests/dashboard/test_static_app_behavior.py
git commit -m "feat: collapse add server card after setup"
```
