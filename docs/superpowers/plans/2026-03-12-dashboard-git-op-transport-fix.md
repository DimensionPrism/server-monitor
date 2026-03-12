# Dashboard Git Op Transport Fix Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route dashboard git operations through the healthy persistent SSH transport and keep one-shot SSH as fallback.

**Architecture:** Add a small runtime helper that prefers `PersistentBatchTransport` for git ops and falls back to the current executor on transport failure. Harden the persistent transport with a per-session lock so same-alias polling and git ops cannot interleave shell requests.

**Tech Stack:** Python 3.13, FastAPI runtime helpers, pytest, asyncio.

---

## Chunk 1: Regression Coverage

### Task 1: Add failing runtime tests for git-op transport selection

**Files:**
- Modify: `tests/dashboard/test_runtime.py`

- [ ] **Step 1: Write failing tests for persistent transport usage**

- [ ] **Step 2: Run `uv run pytest tests/dashboard/test_runtime.py -k "git_op_.*batch_transport" -q`**

- [ ] **Step 3: Confirm the new tests fail for the expected reason**

### Task 2: Add failing persistent-session serialization test

**Files:**
- Modify: `tests/dashboard/test_persistent_session.py`

- [ ] **Step 1: Write failing test for same-session request serialization**

- [ ] **Step 2: Run `uv run pytest tests/dashboard/test_persistent_session.py -k "serializes" -q`**

- [ ] **Step 3: Confirm the new test fails for the expected reason**

## Chunk 2: Minimal Implementation

### Task 3: Route git ops through persistent transport with fallback

**Files:**
- Modify: `src/server_monitor/dashboard/runtime.py`

- [ ] **Step 1: Add a helper that prefers batch transport for git ops**

- [ ] **Step 2: Use that helper for operation and post-op status commands**

- [ ] **Step 3: Keep one-shot executor fallback unchanged**

### Task 4: Serialize same-alias persistent-session requests

**Files:**
- Modify: `src/server_monitor/dashboard/persistent_session.py`

- [ ] **Step 1: Add a session lock**

- [ ] **Step 2: Guard the request write/read cycle with the lock**

## Chunk 3: Verification

### Task 5: Focused regression checks

**Files:**
- Verify: `tests/dashboard/test_runtime.py`
- Verify: `tests/dashboard/test_persistent_session.py`
- Verify: `tests/dashboard/test_settings_api.py`

- [ ] **Step 1: Run `uv run pytest tests/dashboard/test_runtime.py -k "git_op or batch_transport" -q`**

- [ ] **Step 2: Run `uv run pytest tests/dashboard/test_persistent_session.py -q`**

- [ ] **Step 3: Run `uv run pytest tests/dashboard/test_settings_api.py -k "git_ops" -q`**

### Task 6: Live behavior check on a fresh app instance

**Files:**
- Verify: runtime behavior only

- [ ] **Step 1: Start a fresh dashboard instance on a non-default port**

- [ ] **Step 2: Call `refresh`, `fetch`, `pull`, and `checkout main` through the API**

- [ ] **Step 3: Confirm non-refresh ops no longer time out**
