# Dashboard UI Visual Optimization Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the approved summary-first dashboard visual refresh so the monitor view scans faster and the settings view becomes add-first, overview-first, and edit-on-demand.

**Architecture:** Keep the existing FastAPI static frontend and websocket payloads, but refactor the monitor and settings render helpers in `app.js` to emit new UI structure and update `styles.css` to apply the approved visual system. Preserve all current dashboard actions, settings fields, and backend API contracts.

**Tech Stack:** FastAPI static frontend, vanilla JavaScript, CSS, pytest, ruff, uv.

**Workflow Notes:** Use `@test-driven-development` for each code task and `@verification-before-completion` before declaring the work complete.

---

## File Map

- `src/server_monitor/dashboard/static/index.html`
  - Keep the overall page shell, but add any structural containers needed for the redesigned settings workspace.
- `src/server_monitor/dashboard/static/app.js`
  - Own the summary-first monitor markup, settings overview/editor rendering, and client-side UI state for focused settings editing.
- `src/server_monitor/dashboard/static/styles.css`
  - Define the visual system tokens, monitor card hierarchy, GPU tile styling, settings overview list, and focused editor layout.
- `tests/dashboard/test_static_routes.py`
  - Assert static HTML/CSS/JS markers for the new monitor and settings structure so frontend regressions are caught without browser automation.

## Chunk 1: Summary-First Monitor Cards

### Task 1: Add failing static coverage for summary-first monitor hooks

**Files:**
- Modify: `tests/dashboard/test_static_routes.py`
- Test: `tests/dashboard/test_static_routes.py`

- [ ] **Step 1: Write failing tests for the new summary helpers and classes**

```python
def test_app_js_renders_summary_first_monitor_helpers():
    ...
    assert "function renderServerSummary" in response.text
    assert "summary-metric" in response.text
    assert "server-summary-rail" in response.text
```

- [ ] **Step 2: Run the targeted tests to verify they fail**

Run: `uv run pytest tests/dashboard/test_static_routes.py::test_app_js_renders_summary_first_monitor_helpers -q`
Expected: FAIL because the summary-first hooks do not exist yet.

- [ ] **Step 3: Add a second failing test for collapsed detail defaults**

```python
def test_app_js_collapses_monitor_detail_sections_by_default():
    ...
    assert 'renderPanelGroup("System"' in response.text
    assert "open: false" in response.text
```

- [ ] **Step 4: Run both targeted tests and keep them red**

Run: `uv run pytest tests/dashboard/test_static_routes.py -k "summary_first_monitor_helpers or collapses_monitor_detail_sections" -q`
Expected: FAIL.

- [ ] **Step 5: Commit the failing tests**

```bash
git add tests/dashboard/test_static_routes.py
git commit -m "test: require summary-first monitor markup hooks"
```

### Task 2: Implement summary-first monitor rendering in `app.js`

**Files:**
- Modify: `src/server_monitor/dashboard/static/app.js`
- Test: `tests/dashboard/test_static_routes.py`

- [ ] **Step 1: Add small monitor summary helpers**

```javascript
function renderSummaryMetric(label, value, options = {}) {
  ...
}

function renderServerSummary(update, snapshot, freshness) {
  ...
}
```

- [ ] **Step 2: Update `renderMonitor()` to place the summary rail between the card header and detail stack**

```javascript
html = `
  <article class="card server-card">
    <header class="server-card-head">...</header>
    ${renderServerSummary(update, snapshot, freshness)}
    ...
  </article>
`;
```

- [ ] **Step 3: Change detail sections to default closed so the collapsed state stays metrics-only**

```javascript
renderPanelGroup("System", ..., { open: false, ... })
```

- [ ] **Step 4: Run the targeted static tests and verify they pass**

Run: `uv run pytest tests/dashboard/test_static_routes.py -k "summary_first_monitor_helpers or collapses_monitor_detail_sections" -q`
Expected: PASS.

- [ ] **Step 5: Commit the monitor markup refactor**

```bash
git add src/server_monitor/dashboard/static/app.js tests/dashboard/test_static_routes.py
git commit -m "feat: render summary-first monitor cards"
```

## Chunk 2: Overview-First Settings Workspace

### Task 3: Add failing coverage for the settings overview and focused editor flow

**Files:**
- Modify: `tests/dashboard/test_static_routes.py`
- Test: `tests/dashboard/test_static_routes.py`

- [ ] **Step 1: Write failing HTML structure assertions for the settings shell**

```python
def test_root_serves_settings_workspace_shell():
    ...
    assert "settings-overview" in response.text
    assert "settings-editor-panel" in response.text
```

- [ ] **Step 2: Run the targeted HTML test to verify it fails**

Run: `uv run pytest tests/dashboard/test_static_routes.py::test_root_serves_settings_workspace_shell -q`
Expected: FAIL because the shell containers are not in `index.html` yet.

- [ ] **Step 3: Add failing JS assertions for overview/editor rendering state**

```python
def test_app_js_includes_settings_overview_selection_flow():
    ...
    assert "selectedSettingsServerId" in response.text
    assert "renderSettingsOverview" in response.text
    assert "renderSettingsEditorPanel" in response.text
```

- [ ] **Step 4: Run both targeted tests and keep them red**

Run: `uv run pytest tests/dashboard/test_static_routes.py -k "settings_workspace_shell or settings_overview_selection_flow" -q`
Expected: FAIL.

- [ ] **Step 5: Commit the failing settings tests**

```bash
git add tests/dashboard/test_static_routes.py
git commit -m "test: require overview-first settings workspace"
```

### Task 4: Implement the add/overview/edit settings flow

**Files:**
- Modify: `src/server_monitor/dashboard/static/index.html`
- Modify: `src/server_monitor/dashboard/static/app.js`
- Test: `tests/dashboard/test_static_routes.py`

- [ ] **Step 1: Add structural containers in `index.html` for add, overview, and focused editor regions**

```html
<section class="settings-shell">
  <div class="settings-add-card">...</div>
  <div id="settings-overview" class="settings-overview"></div>
  <div id="settings-editor-panel" class="settings-editor-panel"></div>
</section>
```

- [ ] **Step 2: Add client-side state for the selected server in Settings**

```javascript
const state = {
  ...
  selectedSettingsServerId: null,
};
```

- [ ] **Step 3: Split settings rendering into overview rows plus a dedicated editor panel**

```javascript
function renderSettingsOverview() { ... }
function renderSettingsEditorPanel() { ... }
```

- [ ] **Step 4: Run the targeted settings tests and verify they pass**

Run: `uv run pytest tests/dashboard/test_static_routes.py -k "settings_workspace_shell or settings_overview_selection_flow" -q`
Expected: PASS.

- [ ] **Step 5: Commit the settings workspace refactor**

```bash
git add src/server_monitor/dashboard/static/index.html src/server_monitor/dashboard/static/app.js tests/dashboard/test_static_routes.py
git commit -m "feat: restructure settings into add overview and focused edit flows"
```

## Chunk 3: Visual System and Surface Polish

### Task 5: Add failing style coverage for the new visual system

**Files:**
- Modify: `tests/dashboard/test_static_routes.py`
- Test: `tests/dashboard/test_static_routes.py`

- [ ] **Step 1: Add failing CSS marker assertions for the new tokens and layout classes**

```python
def test_styles_css_exposes_summary_and_settings_visual_tokens():
    ...
    assert "--surface-0" in response.text
    assert ".server-summary-rail" in response.text
    assert ".settings-overview-row" in response.text
```

- [ ] **Step 2: Run the targeted CSS test to verify it fails**

Run: `uv run pytest tests/dashboard/test_static_routes.py::test_styles_css_exposes_summary_and_settings_visual_tokens -q`
Expected: FAIL.

- [ ] **Step 3: Add a second failing CSS test for GPU and focused-editor layout markers**

```python
def test_styles_css_has_gpu_tile_and_editor_panel_rules():
    ...
    assert ".gpu-card" in response.text
    assert ".settings-editor-panel" in response.text
```

- [ ] **Step 4: Run both targeted CSS tests and keep them red**

Run: `uv run pytest tests/dashboard/test_static_routes.py -k "summary_and_settings_visual_tokens or gpu_tile_and_editor_panel_rules" -q`
Expected: FAIL.

- [ ] **Step 5: Commit the failing CSS tests**

```bash
git add tests/dashboard/test_static_routes.py
git commit -m "test: require visual refresh style markers"
```

### Task 6: Implement the visual refresh in `styles.css`

**Files:**
- Modify: `src/server_monitor/dashboard/static/styles.css`
- Modify: `src/server_monitor/dashboard/static/index.html` (only if extra classes are required)
- Modify: `src/server_monitor/dashboard/static/app.js` (only if extra style hooks are required)
- Test: `tests/dashboard/test_static_routes.py`

- [ ] **Step 1: Replace the current global tokens with calmer surfaces, semantic colors, and dual-font stacks**

```css
:root {
  --surface-0: ...;
  --surface-1: ...;
  --accent: ...;
}
```

- [ ] **Step 2: Style the summary-first monitor surface, including metric blocks and collapsed/expanded card behavior**

```css
.server-summary-rail { ... }
.summary-metric { ... }
.server-card[open] { ... }
```

- [ ] **Step 3: Style the GPU grid and settings workspace to match the approved hierarchy**

```css
.gpu-grid { ... }
.settings-overview-row { ... }
.settings-editor-panel { ... }
```

- [ ] **Step 4: Run the targeted static tests and verify they pass**

Run: `uv run pytest tests/dashboard/test_static_routes.py -k "summary_and_settings_visual_tokens or gpu_tile_and_editor_panel_rules" -q`
Expected: PASS.

- [ ] **Step 5: Commit the visual system refactor**

```bash
git add src/server_monitor/dashboard/static/styles.css src/server_monitor/dashboard/static/index.html src/server_monitor/dashboard/static/app.js tests/dashboard/test_static_routes.py
git commit -m "feat: apply summary-first dashboard visual system"
```

## Chunk 4: Verification and Smoke Test

### Task 7: Run project verification and manual UI smoke test

**Files:**
- No required code changes; verification only.

- [ ] **Step 1: Run lint**

Run: `uv run ruff check .`
Expected: no issues.

- [ ] **Step 2: Run the full test suite**

Run: `uv run pytest -q`
Expected: all tests pass.

- [ ] **Step 3: Run the dashboard locally for a manual browser pass**

Run: `uv run uvicorn server_monitor.dashboard.main:build_dashboard_app --factory --host 127.0.0.1 --port 8080`
Expected: the dashboard loads at `http://127.0.0.1:8080`.

- [ ] **Step 4: Manually verify the approved UX outcomes**

Check:
- collapsed monitor cards show metrics only
- GPU panel is readable for 8+ devices
- settings separates add, overview, and focused edit flows
- focus and hover states are obvious on keyboard and pointer input

- [ ] **Step 5: Commit any final verification-driven cleanup**

```bash
git add src/server_monitor/dashboard/static/index.html src/server_monitor/dashboard/static/app.js src/server_monitor/dashboard/static/styles.css tests/dashboard/test_static_routes.py
git commit -m "chore: finalize dashboard ui visual optimization"
```
