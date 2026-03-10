# Agentless Monitor Dashboard v1 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace remote-agent dependency with local SSH polling and add interactive settings UI for server/panel/working-directory management.

**Architecture:** One local FastAPI app maintains a background SSH polling runtime, persists settings in `config/servers.toml`, and streams normalized snapshots to browser clients over WebSocket.

**Tech Stack:** Python (`uv`, FastAPI, httpx, asyncio), TOML config persistence, vanilla HTML/CSS/JS UI.

---

## Chunk 1: Settings Model and Runtime Pivot

### Task 1: Add settings data model and file store

**Files:**
- Create: `src/server_monitor/dashboard/settings.py`
- Test: `tests/dashboard/test_settings_store.py`

- [ ] **Step 1: Write failing tests for load/save/create/update/delete behavior**
- [ ] **Step 2: Run tests to verify they fail**
- [ ] **Step 3: Implement typed settings models + atomic save**
- [ ] **Step 4: Re-run tests to green**
- [ ] **Step 5: Commit**

### Task 2: Replace HTTP-agent polling runtime with SSH polling runtime

**Files:**
- Modify: `src/server_monitor/dashboard/runtime.py`
- Test: `tests/dashboard/test_runtime.py`

- [ ] **Step 1: Write failing tests for SSH executor integration and panel propagation**
- [ ] **Step 2: Run tests to verify fail**
- [ ] **Step 3: Implement SSH-based runtime polling from settings store**
- [ ] **Step 4: Re-run tests to green**
- [ ] **Step 5: Commit**

## Chunk 2: API and Interactive Settings UI

### Task 3: Add settings CRUD API endpoints

**Files:**
- Modify: `src/server_monitor/dashboard/api.py`
- Modify: `src/server_monitor/dashboard/main.py`
- Test: `tests/dashboard/test_settings_api.py`

- [ ] **Step 1: Write failing API tests for GET/POST/PUT/DELETE settings operations**
- [ ] **Step 2: Run tests to verify fail**
- [ ] **Step 3: Implement settings API endpoints and wire store/runtime**
- [ ] **Step 4: Re-run tests to green**
- [ ] **Step 5: Commit**

### Task 4: Build interactive settings UI

**Files:**
- Modify: `src/server_monitor/dashboard/static/index.html`
- Modify: `src/server_monitor/dashboard/static/app.js`
- Modify: `src/server_monitor/dashboard/static/styles.css`
- Test: `tests/dashboard/test_static_routes.py`

- [ ] **Step 1: Write/adjust failing UI contract test where needed**
- [ ] **Step 2: Run test(s) to verify fail**
- [ ] **Step 3: Implement settings tab with server and working-directory CRUD + panel toggles**
- [ ] **Step 4: Re-run test(s) to green**
- [ ] **Step 5: Commit**

## Chunk 3: Docs and Verification

### Task 5: Update configs/docs for agentless workflow

**Files:**
- Modify: `config/local-dashboard.example.toml`
- Create: `config/servers.example.toml`
- Modify: `README.md`

- [ ] **Step 1: Write/adjust failing docs/config test if needed**
- [ ] **Step 2: Implement agentless setup instructions and examples**
- [ ] **Step 3: Verify end-to-end local smoke commands**
- [ ] **Step 4: Commit**

### Task 6: Full verification and handoff

**Files:**
- Verify only

- [ ] **Step 1: Run full test suite**
Run: `uv run pytest -q`
Expected: PASS

- [ ] **Step 2: Run lint**
Run: `uv run ruff check .`
Expected: PASS

- [ ] **Step 3: Confirm clean git status and summarize**

