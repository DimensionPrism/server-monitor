# Safe Git Ops v1 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add guarded git operations (refresh/fetch/pull/checkout) to the agentless dashboard API and UI for configured repos.

**Architecture:** Add a runtime git-op entrypoint that validates scope and runs only allowlisted commands over SSH. Expose one API endpoint for git ops and wire frontend controls in the Git panel to trigger operations and apply immediate status updates.

**Tech Stack:** Python 3.12, FastAPI, pytest, vanilla JS/CSS, uv.

---

## Chunk 1: Backend Safe Ops API + Runtime

### Task 1: Runtime git operation primitive

**Files:**
- Modify: `src/server_monitor/dashboard/runtime.py`
- Test: `tests/dashboard/test_runtime.py`

- [ ] **Step 1: Write failing tests for runtime git ops behavior**

```python
def test_runtime_git_op_blocks_unconfigured_repo():
    ...

def test_runtime_git_op_runs_fetch_and_returns_refreshed_repo():
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/dashboard/test_runtime.py -q`
Expected: FAIL for missing runtime git op API.

- [ ] **Step 3: Write minimal runtime implementation**

```python
async def run_git_operation(...):
    # validate server and repo, run allowlisted command, refresh status
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/dashboard/test_runtime.py -q`
Expected: PASS for new runtime git op tests.

- [ ] **Step 5: Commit**

```bash
git add tests/dashboard/test_runtime.py src/server_monitor/dashboard/runtime.py
git commit -m "feat: add safe git operation runtime primitive"
```

### Task 2: API endpoint for safe git ops

**Files:**
- Modify: `src/server_monitor/dashboard/api.py`
- Test: `tests/dashboard/test_settings_api.py`

- [ ] **Step 1: Write failing API tests**

```python
def test_git_ops_endpoint_executes_safe_operation():
    ...

def test_git_ops_endpoint_rejects_invalid_operation():
    ...
```

- [ ] **Step 2: Run tests to verify failures**

Run: `uv run pytest tests/dashboard/test_settings_api.py -q`
Expected: FAIL for missing `/api/servers/{server_id}/git/ops` route.

- [ ] **Step 3: Implement minimal API route + payload validation**

```python
@app.post("/api/servers/{server_id}/git/ops")
def run_git_op(...):
    ...
```

- [ ] **Step 4: Re-run tests to verify pass**

Run: `uv run pytest tests/dashboard/test_settings_api.py -q`
Expected: PASS for git-ops endpoint tests.

- [ ] **Step 5: Commit**

```bash
git add tests/dashboard/test_settings_api.py src/server_monitor/dashboard/api.py
git commit -m "feat: expose safe git ops api endpoint"
```

## Chunk 2: Frontend Controls + Styling

### Task 3: Git panel controls and client actions

**Files:**
- Modify: `src/server_monitor/dashboard/static/index.html`
- Modify: `src/server_monitor/dashboard/static/app.js`
- Modify: `src/server_monitor/dashboard/static/styles.css`
- Test: `tests/e2e/test_dashboard_websocket_runtime.py` (or existing UI-facing smoke tests as applicable)

- [ ] **Step 1: Write/extend failing UI-facing test(s)**

```python
def test_monitor_git_panel_renders_safe_ops_controls():
    ...
```

- [ ] **Step 2: Run targeted tests to verify failure**

Run: `uv run pytest tests/e2e/test_dashboard_websocket_runtime.py -q`
Expected: FAIL until controls/handlers are added.

- [ ] **Step 3: Implement frontend controls and optimistic status updates**

```javascript
// add per-repo controls + operation handler
```

- [ ] **Step 4: Re-run targeted tests**

Run: `uv run pytest tests/e2e/test_dashboard_websocket_runtime.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/server_monitor/dashboard/static/index.html src/server_monitor/dashboard/static/app.js src/server_monitor/dashboard/static/styles.css tests/e2e/test_dashboard_websocket_runtime.py
git commit -m "feat: add safe git controls to dashboard git panel"
```

## Chunk 3: Final Verification + Docs

### Task 4: Docs and full verification

**Files:**
- Modify: `README.md`
- Optional: `config/servers.example.toml`

- [ ] **Step 1: Update docs for safe ops and guardrails**
- [ ] **Step 2: Run lint and full tests**

Run: `uv run ruff check .`
Expected: no issues

Run: `uv run pytest -q`
Expected: all pass

- [ ] **Step 3: Commit docs + verification-ready state**

```bash
git add README.md config/servers.example.toml
git commit -m "docs: document safe git operations in dashboard"
```