# Monitor UI Density Redesign (A1) Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the approved A1 monitor UI with side-by-side server cards, nested collapsible sections, and auto-fit GPU tiles for any GPU count.

**Architecture:** Keep existing websocket payload and rendering pipeline, but restructure monitor markup generation in `app.js` to emit nested `<details>` sections and update CSS for board/card/section hierarchy. Preserve existing git operation flows and API contracts.

**Tech Stack:** FastAPI static frontend, vanilla JavaScript, CSS, pytest, ruff, uv.

---

## Chunk 1: Markup and Render Structure

### Task 1: Add failing static test coverage for nested monitor structure

**Files:**
- Modify: `tests/dashboard/test_static_routes.py`
- Test: `tests/dashboard/test_static_routes.py`

- [ ] **Step 1: Write failing tests**

```python
def test_app_js_uses_nested_monitor_sections():
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/dashboard/test_static_routes.py::test_app_js_uses_nested_monitor_sections -q`
Expected: FAIL because nested section markers are missing.

- [ ] **Step 3: Implement minimal test scaffolding updates**
- [ ] **Step 4: Re-run test to keep it red until UI code changes**

Run: `uv run pytest tests/dashboard/test_static_routes.py::test_app_js_uses_nested_monitor_sections -q`
Expected: FAIL.

- [ ] **Step 5: Commit test-only changes**

```bash
git add tests/dashboard/test_static_routes.py
git commit -m "test: add coverage for nested monitor section markup"
```

### Task 2: Implement nested sections in monitor renderer

**Files:**
- Modify: `src/server_monitor/dashboard/static/app.js`
- Test: `tests/dashboard/test_static_routes.py`

- [ ] **Step 1: Write/extend failing assertions for section defaults**

```python
def test_app_js_nested_sections_have_expected_default_open_state():
    ...
```

- [ ] **Step 2: Run targeted tests (verify red)**

Run: `uv run pytest tests/dashboard/test_static_routes.py -q`
Expected: FAIL for missing section/default markers.

- [ ] **Step 3: Implement minimal nested rendering**

```javascript
// renderServerSection(title, body, options)
// use <details open> for System/GPU and collapsed for Git/Clash
```

- [ ] **Step 4: Run targeted tests (verify green)**

Run: `uv run pytest tests/dashboard/test_static_routes.py -q`
Expected: PASS.

- [ ] **Step 5: Commit markup changes**

```bash
git add src/server_monitor/dashboard/static/app.js tests/dashboard/test_static_routes.py
git commit -m "feat: render monitor panels as nested collapsible sections"
```

## Chunk 2: Visual Density and GPU Auto-Fit Grid

### Task 3: Add failing style coverage for A1 layout and GPU auto-fit

**Files:**
- Modify: `tests/dashboard/test_static_routes.py`
- Test: `tests/dashboard/test_static_routes.py`

- [ ] **Step 1: Write failing style-marker test**

```python
def test_styles_css_has_server_board_and_gpu_autofit_grid_rules():
    ...
```

- [ ] **Step 2: Run test to verify red**

Run: `uv run pytest tests/dashboard/test_static_routes.py::test_styles_css_has_server_board_and_gpu_autofit_grid_rules -q`
Expected: FAIL.

- [ ] **Step 3: Keep tests failing until CSS updates land**
- [ ] **Step 4: Commit test updates**

```bash
git add tests/dashboard/test_static_routes.py
git commit -m "test: require A1 layout and gpu autofit style markers"
```

### Task 4: Implement A1 board + dense nested styling

**Files:**
- Modify: `src/server_monitor/dashboard/static/styles.css`
- Modify: `src/server_monitor/dashboard/static/index.html` (only if structure hooks needed)
- Test: `tests/dashboard/test_static_routes.py`

- [ ] **Step 1: Implement minimal CSS for A1 + nested depth + auto-fit GPU**

```css
.server-board { ... }
.server-card { ... }
.nested-section { ... }
.gpu-grid { grid-template-columns: repeat(auto-fit, minmax(...)); }
```

- [ ] **Step 2: Run targeted static tests**

Run: `uv run pytest tests/dashboard/test_static_routes.py -q`
Expected: PASS.

- [ ] **Step 3: Commit style changes**

```bash
git add src/server_monitor/dashboard/static/styles.css src/server_monitor/dashboard/static/index.html tests/dashboard/test_static_routes.py
git commit -m "feat: apply A1 multi-server board and dense nested styling"
```

## Chunk 3: Final Verification

### Task 5: Full suite and lint verification

**Files:**
- No required code changes; verification only.

- [ ] **Step 1: Run lint**

Run: `uv run ruff check .`
Expected: no issues.

- [ ] **Step 2: Run full tests**

Run: `uv run pytest -q`
Expected: all pass.

- [ ] **Step 3: Optional README note if layout model changed materially**

```bash
git add README.md
git commit -m "docs: note monitor A1 nested layout behavior"
```