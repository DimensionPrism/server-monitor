# Dashboard UI Premium Refinement Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the approved premium dashboard refinement so the monitor feels more polished and the settings workspace becomes a stronger split-view editing surface without changing backend behavior.

**Architecture:** Keep the existing FastAPI static frontend and current websocket/settings data contracts, but refine `index.html`, `app.js`, and `styles.css` to render a richer settings workspace and a more premium monitor surface. Preserve the current summary-first monitor structure, GPU summary semantics, and per-server settings draft behavior while extending tests to lock down the new markup and UI-state hooks.

**Tech Stack:** FastAPI static frontend, vanilla JavaScript, CSS, pytest, ruff, uv.

**Workflow Notes:** Use `@test-driven-development` for each code task and `@verification-before-completion` before claiming completion.

---

## File Map

- `src/server_monitor/dashboard/static/index.html`
  - Add any structural wrappers needed for the split settings workspace and sticky editor footer.
- `src/server_monitor/dashboard/static/app.js`
  - Own the updated settings workspace rendering, sticky footer state hooks, semantic summary/meter classes, and motion-related state attributes.
- `src/server_monitor/dashboard/static/styles.css`
  - Extend the premium visual system tokens, transitions, semantic meter states, GPU heat styling, and split settings layout.
- `tests/dashboard/test_static_routes.py`
  - Assert new HTML/CSS/JS hooks for the premium refinement without needing a browser.
- `tests/dashboard/test_static_app_behavior.py`
  - Cover dirty/clean footer behavior and rendering rules that can be tested through the existing Node-backed path.

## Chunk 1: Settings Workspace Structure

### Task 1: Add failing coverage for the split settings workspace shell

**Files:**
- Modify: `tests/dashboard/test_static_routes.py`
- Test: `tests/dashboard/test_static_routes.py`

- [ ] **Step 1: Write failing HTML assertions for the split settings workspace**

```python
def test_root_serves_split_settings_workspace_shell():
    response = client.get("/")
    assert "settings-workspace-grid" in response.text
    assert "settings-overview-rail" in response.text
    assert "settings-editor-canvas" in response.text
    assert "settings-editor-footer" in response.text
```

- [ ] **Step 2: Run the targeted test to verify it fails**

Run: `uv run pytest tests/dashboard/test_static_routes.py::test_root_serves_split_settings_workspace_shell -q`
Expected: FAIL because the new workspace hooks do not exist yet.

- [ ] **Step 3: Add failing JS assertions for grouped editor-card rendering hooks**

```python
def test_app_js_includes_grouped_settings_editor_hooks():
    response = client.get("/static/app.js")
    assert "settings-editor-card" in response.text
    assert "settings-editor-footer" in response.text
    assert "data-dirty-state" in response.text
```

- [ ] **Step 4: Run both targeted tests and keep them red**

Run: `uv run pytest tests/dashboard/test_static_routes.py -k "split_settings_workspace_shell or grouped_settings_editor_hooks" -q`
Expected: FAIL.

- [ ] **Step 5: Commit the failing shell tests**

```bash
git add tests/dashboard/test_static_routes.py
git commit -m "test: require premium settings workspace hooks"
```

### Task 2: Implement the split settings workspace and grouped editor cards

**Files:**
- Modify: `src/server_monitor/dashboard/static/index.html`
- Modify: `src/server_monitor/dashboard/static/app.js`
- Test: `tests/dashboard/test_static_routes.py`

- [ ] **Step 1: Add split-workspace containers in `index.html`**

```html
<section class="settings-shell">
  <div class="settings-add-card">
    <h2>Server Settings</h2>
    <form id="add-server-form" class="settings-form"></form>
  </div>
  <div class="settings-workspace-grid">
    <div class="settings-overview-rail">
      <div id="settings-overview" class="settings-overview"></div>
    </div>
    <div id="settings-editor-panel" class="settings-editor-canvas"></div>
  </div>
</section>
```

- [ ] **Step 2: Refactor the selected-server editor template into grouped cards**

```javascript
function renderSettingsEditorCards(server) {
  return `
    <section class="settings-editor-card settings-editor-card-identity"></section>
    <section class="settings-editor-card settings-editor-card-targets"></section>
    <div class="settings-editor-row">
      <section class="settings-editor-card settings-editor-card-panels"></section>
      <section class="settings-editor-card settings-editor-card-probes"></section>
    </div>
  `;
}
```

- [ ] **Step 3: Add a sticky editor footer hook with save/delete/status regions**

```javascript
function renderSettingsEditorFooter({ dirty }) {
  return `
    <footer class="settings-editor-footer" data-dirty-state="${dirty ? "dirty" : "clean"}">
      <div class="settings-editor-footer-status" data-role="status"></div>
      <div class="settings-editor-footer-actions">
        <button class="btn-primary" data-action="save" type="button">Save</button>
        <button class="btn-danger" data-action="delete" type="button">Delete</button>
      </div>
    </footer>
  `;
}
```

- [ ] **Step 4: Run the targeted workspace tests and verify they pass**

Run: `uv run pytest tests/dashboard/test_static_routes.py -k "split_settings_workspace_shell or grouped_settings_editor_hooks" -q`
Expected: PASS.

- [ ] **Step 5: Commit the workspace structure refactor**

```bash
git add src/server_monitor/dashboard/static/index.html src/server_monitor/dashboard/static/app.js tests/dashboard/test_static_routes.py
git commit -m "feat: restructure settings into premium split workspace"
```

## Chunk 2: Settings State and Footer Behavior

### Task 3: Add failing behavior coverage for dirty footer states

**Files:**
- Modify: `tests/dashboard/test_static_app_behavior.py`
- Test: `tests/dashboard/test_static_app_behavior.py`

- [ ] **Step 1: Add a failing behavior test for clean vs dirty footer state**

```python
def test_settings_editor_footer_reflects_dirty_state(node_static_app):
    script = """
    // render clean footer, mutate draft, rerender, assert dirty state marker
    """
    result = node_static_app(script)
    assert result["cleanState"] == "clean"
    assert result["dirtyState"] == "dirty"
```

- [ ] **Step 2: Run the targeted behavior test to verify it fails**

Run: `uv run pytest tests/dashboard/test_static_app_behavior.py::test_settings_editor_footer_reflects_dirty_state -q`
Expected: FAIL because the footer state hook is not wired yet.

- [ ] **Step 3: Add a second failing behavior test for preserving drafts through split-view selection**

```python
def test_settings_split_view_keeps_drafts_when_switching_rows(node_static_app):
    script = """
    // edit server A, switch to server B, switch back, assert draft preserved
    """
    result = node_static_app(script)
    assert result["firstDraftAlias"] == "edited-alias"
```

- [ ] **Step 4: Run both targeted behavior tests and keep them red**

Run: `uv run pytest tests/dashboard/test_static_app_behavior.py -k "footer_reflects_dirty_state or split_view_keeps_drafts" -q`
Expected: FAIL.

- [ ] **Step 5: Commit the failing behavior tests**

```bash
git add tests/dashboard/test_static_app_behavior.py
git commit -m "test: require premium settings footer behavior"
```

### Task 4: Implement sticky-footer state handling and editor transitions

**Files:**
- Modify: `src/server_monitor/dashboard/static/app.js`
- Modify: `src/server_monitor/dashboard/static/styles.css`
- Test: `tests/dashboard/test_static_app_behavior.py`

- [ ] **Step 1: Add helpers to compute editor dirty state from the current draft**

```javascript
function isServerDraftDirty(server, draft) {
  const baseline = createSettingsDraft(server);
  return JSON.stringify(normalizeDraftForCompare(draft)) !== JSON.stringify(normalizeDraftForCompare(baseline));
}
```

- [ ] **Step 2: Render sticky-footer state and wire it to selection/save flows**

```javascript
const draft = readSettingsDraft(selectedServer);
const dirty = isServerDraftDirty(selectedServer, draft);
panel.innerHTML = `${renderSettingsEditorCards(selectedServer)}${renderSettingsEditorFooter({ dirty })}`;
```

- [ ] **Step 3: Add CSS states and transitions for clean, dirty, and saved footer presentation**

```css
.settings-editor-footer[data-dirty-state="dirty"] { border-color: rgba(34, 211, 238, 0.34); box-shadow: 0 18px 36px rgba(14, 165, 233, 0.14); }
.settings-editor-footer[data-save-state="saved"] { color: #8fdcff; }
```

- [ ] **Step 4: Run the targeted behavior tests and verify they pass**

Run: `uv run pytest tests/dashboard/test_static_app_behavior.py -k "footer_reflects_dirty_state or split_view_keeps_drafts" -q`
Expected: PASS.

- [ ] **Step 5: Commit the footer-state implementation**

```bash
git add src/server_monitor/dashboard/static/app.js src/server_monitor/dashboard/static/styles.css tests/dashboard/test_static_app_behavior.py
git commit -m "feat: add premium settings footer states"
```

## Chunk 3: Premium Monitor Styling

### Task 5: Add failing coverage for premium monitor style hooks

**Files:**
- Modify: `tests/dashboard/test_static_routes.py`
- Test: `tests/dashboard/test_static_routes.py`

- [ ] **Step 1: Add failing CSS assertions for premium meter and GPU heat classes**

```python
def test_styles_css_exposes_premium_monitor_classes():
    response = client.get("/static/styles.css")
    assert ".summary-metric[data-level=" in response.text
    assert ".meter-fill[data-level=" in response.text
    assert ".gpu-card[data-heat=" in response.text
```

- [ ] **Step 2: Run the targeted CSS test to verify it fails**

Run: `uv run pytest tests/dashboard/test_static_routes.py::test_styles_css_exposes_premium_monitor_classes -q`
Expected: FAIL.

- [ ] **Step 3: Add failing JS assertions for semantic summary and GPU heat helpers**

```python
def test_app_js_includes_semantic_summary_and_gpu_heat_helpers():
    response = client.get("/static/app.js")
    assert "getUtilizationLevel" in response.text
    assert "getGpuHeatLevel" in response.text
```

- [ ] **Step 4: Run both targeted tests and keep them red**

Run: `uv run pytest tests/dashboard/test_static_routes.py -k "premium_monitor_classes or semantic_summary_and_gpu_heat_helpers" -q`
Expected: FAIL.

- [ ] **Step 5: Commit the failing monitor-style tests**

```bash
git add tests/dashboard/test_static_routes.py
git commit -m "test: require premium monitor styling hooks"
```

### Task 6: Implement semantic monitor styling and GPU heat cues

**Files:**
- Modify: `src/server_monitor/dashboard/static/app.js`
- Modify: `src/server_monitor/dashboard/static/styles.css`
- Test: `tests/dashboard/test_static_routes.py`

- [ ] **Step 1: Add summary and meter-level semantic helpers in `app.js`**

```javascript
function getUtilizationLevel(percent) {
  if (percent >= 90) return "danger";
  if (percent >= 70) return "warn";
  return "ok";
}

function getGpuHeatLevel(temperature) {
  if (temperature >= 85) return "hot";
  if (temperature >= 75) return "warm";
  return "cool";
}
```

- [ ] **Step 2: Attach semantic data attributes to summary metrics, meter fills, and GPU cards**

```javascript
<div class="summary-metric" data-level="${level}">
  <div class="summary-metric-value">${value}</div>
</div>
<div class="meter-fill" data-level="${level}"></div>
<article class="gpu-card" data-heat="${heatLevel}"></article>
```

- [ ] **Step 3: Extend CSS with premium surfaces, always-on semantic color, and local GPU heat styling**

```css
.summary-metric[data-level="warn"] { border-color: rgba(245, 158, 11, 0.28); }
.meter-fill[data-level="danger"] { background: linear-gradient(90deg, #f59e0b, #ef4444); }
.gpu-card[data-heat="hot"] { box-shadow: inset 0 0 0 1px rgba(239, 68, 68, 0.26); }
```

- [ ] **Step 4: Run the targeted monitor-style tests and verify they pass**

Run: `uv run pytest tests/dashboard/test_static_routes.py -k "premium_monitor_classes or semantic_summary_and_gpu_heat_helpers" -q`
Expected: PASS.

- [ ] **Step 5: Commit the premium monitor styling**

```bash
git add src/server_monitor/dashboard/static/app.js src/server_monitor/dashboard/static/styles.css tests/dashboard/test_static_routes.py
git commit -m "feat: add premium semantic monitor styling"
```

## Chunk 4: Motion, Polish, and Verification

### Task 7: Add failing coverage for motion and transition hooks

**Files:**
- Modify: `tests/dashboard/test_static_routes.py`
- Test: `tests/dashboard/test_static_routes.py`

- [ ] **Step 1: Add failing CSS assertions for detail, card, and button motion hooks**

```python
def test_styles_css_has_motion_hooks_for_premium_refinement():
    response = client.get("/static/styles.css")
    assert ".panel-group" in response.text
    assert "transition: max-height" in response.text
    assert ".settings-overview-row:active" in response.text
```

- [ ] **Step 2: Run the targeted motion test to verify it fails**

Run: `uv run pytest tests/dashboard/test_static_routes.py::test_styles_css_has_motion_hooks_for_premium_refinement -q`
Expected: FAIL if the specific premium motion hooks are missing.

- [ ] **Step 3: Add a failing JS assertion for transition-state attributes if needed**

```python
def test_app_js_marks_editor_transition_state():
    response = client.get("/static/app.js")
    assert "data-transition-state" in response.text
```

- [ ] **Step 4: Run both targeted tests and keep them red**

Run: `uv run pytest tests/dashboard/test_static_routes.py -k "motion_hooks_for_premium_refinement or marks_editor_transition_state" -q`
Expected: FAIL.

- [ ] **Step 5: Commit the failing motion tests**

```bash
git add tests/dashboard/test_static_routes.py
git commit -m "test: require premium motion hooks"
```

### Task 8: Implement motion polish and run full verification

**Files:**
- Modify: `src/server_monitor/dashboard/static/styles.css`
- Modify: `src/server_monitor/dashboard/static/app.js` (only if transition-state hooks are needed)
- Test: `tests/dashboard/test_static_routes.py`
- Test: `tests/dashboard/test_static_app_behavior.py`

- [ ] **Step 1: Add refined transitions for details, cards, metrics, and controls**

```css
.panel-group,
.summary-metric,
.settings-overview-row,
.btn-primary,
.btn-danger {
  transition: transform 160ms ease, box-shadow 160ms ease, border-color 160ms ease, background-color 160ms ease;
}
```

- [ ] **Step 2: Add any minimal state hooks needed to coordinate editor or section transitions**

```javascript
panel.dataset.transitionState = "entering";
```

- [ ] **Step 3: Run the targeted motion tests and verify they pass**

Run: `uv run pytest tests/dashboard/test_static_routes.py -k "motion_hooks_for_premium_refinement or marks_editor_transition_state" -q`
Expected: PASS.

- [ ] **Step 4: Run lint and the full test suite**

Run: `uv run ruff check .`
Expected: PASS.

Run: `uv run pytest -q`
Expected: PASS.

- [ ] **Step 5: Run a manual browser smoke test on a non-conflicting port**

Run: `uv run uvicorn server_monitor.dashboard.main:build_dashboard_app --factory --host 127.0.0.1 --port 18081`
Expected: dashboard loads at `http://127.0.0.1:18081`.

Check:
- add-server card is always visible
- overview rail and focused editor split correctly on desktop
- sticky footer reflects clean/dirty/saved states
- summary metrics stay semantically colored
- GPU heat cues stay local to GPU contexts
- motion feels polished without becoming noisy

- [ ] **Step 6: Commit final polish and verification-driven cleanup**

```bash
git add src/server_monitor/dashboard/static/index.html src/server_monitor/dashboard/static/app.js src/server_monitor/dashboard/static/styles.css tests/dashboard/test_static_routes.py tests/dashboard/test_static_app_behavior.py
git commit -m "feat: complete premium dashboard refinement"
```
