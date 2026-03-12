# v1.3 Dashboard Transport Latency Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lower dashboard card latency by batching per-server polls and then adding persistent per-alias SSH sessions, without reducing freshness or card detail.

**Architecture:** First add a batch protocol that lets one SSH command carry multiple logical card results and lets the runtime reconstruct independent outcomes for cache and diagnostics. Then add a persistent SSH session transport per alias so those batched polls stop paying repeated connection setup cost, while preserving one-shot SSH as the automatic fallback path.

**Tech Stack:** Python 3.12, asyncio, FastAPI runtime, existing SSH command runner, pytest, ruff.

---

## File Structure

- Create: `src/server_monitor/dashboard/batch_protocol.py`
  - Build and parse section-delimited batch envelopes for metrics and status polls.
- Create: `src/server_monitor/dashboard/persistent_session.py`
  - Manage long-lived per-alias SSH subprocesses with framed request/response handling.
- Modify: `src/server_monitor/dashboard/runtime.py`
  - Replace per-card SSH polling with batch-based polling and wire in persistent-session transport fallback.
- Modify: `src/server_monitor/dashboard/command_runner.py`
  - Reuse or extend command result helpers needed by the persistent-session transport.
- Modify: `src/server_monitor/dashboard/main.py`
  - Instantiate the updated executor/transport stack.
- Create: `tests/dashboard/test_batch_protocol.py`
  - Unit tests for batch framing and parser behavior.
- Create: `tests/dashboard/test_persistent_session.py`
  - Unit tests for persistent session lifecycle, restart, and fallback behavior.
- Modify: `tests/dashboard/test_runtime.py`
  - Runtime integration tests for batched metrics, batched status, failure isolation, and transport fallback.
- Modify: `README.md`
  - Document the new transport strategy and how to verify it.

## Chunk 1: Batch Protocol

### Task 1: Add failing tests for batch parsing and malformed envelope detection

**Files:**
- Create: `tests/dashboard/test_batch_protocol.py`
- Create: `src/server_monitor/dashboard/batch_protocol.py`

- [ ] **Step 1: Write the failing parser tests**

Create `tests/dashboard/test_batch_protocol.py` with tests like:

```python
from server_monitor.dashboard.batch_protocol import BatchSection, parse_batch_output


def test_parse_batch_output_returns_sections_in_order():
    token = "SMTOKEN"
    output = (
        "SMTOKEN BEGIN kind=system target=server exit=0 duration_ms=123 stream=stdout\n"
        "CPU: 11.0\n"
        "SMTOKEN END\n"
    )

    sections = parse_batch_output(output, token=token)

    assert sections == [
        BatchSection(
            kind="system",
            target="server",
            exit_code=0,
            duration_ms=123,
            stream="stdout",
            payload="CPU: 11.0\n",
        )
    ]


def test_parse_batch_output_rejects_missing_end_marker():
    ...
```

- [ ] **Step 2: Run the protocol tests to verify RED**

Run: `uv run pytest tests/dashboard/test_batch_protocol.py -q`

Expected: FAIL with import errors because `batch_protocol.py` does not exist yet.

- [ ] **Step 3: Implement the minimal batch protocol module**

Create `src/server_monitor/dashboard/batch_protocol.py` with:

```python
from dataclasses import dataclass


@dataclass(slots=True)
class BatchSection:
    kind: str
    target: str
    exit_code: int
    duration_ms: int
    stream: str
    payload: str
```

Also add:

- token generation helper
- metadata parsing helper
- `parse_batch_output(...)`
- explicit exceptions for malformed envelopes

- [ ] **Step 4: Re-run the protocol tests**

Run: `uv run pytest tests/dashboard/test_batch_protocol.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/dashboard/test_batch_protocol.py src/server_monitor/dashboard/batch_protocol.py
git commit -m "feat: add dashboard batch protocol parser"
```

### Task 2: Add builders for metrics and status batch scripts

**Files:**
- Modify: `src/server_monitor/dashboard/batch_protocol.py`
- Modify: `tests/dashboard/test_batch_protocol.py`

- [ ] **Step 1: Add failing tests for script generation**

Extend `tests/dashboard/test_batch_protocol.py` with tests that assert:

- metrics batch includes both system and GPU commands
- status batch includes all configured repo paths
- status batch includes clash secret and clash probe commands
- marker token is embedded in the output framing

- [ ] **Step 2: Run the new batch builder tests to verify RED**

Run: `uv run pytest tests/dashboard/test_batch_protocol.py -k "metrics or status" -q`

Expected: FAIL because the script-builder helpers do not exist yet.

- [ ] **Step 3: Implement minimal batch script builders**

Add to `src/server_monitor/dashboard/batch_protocol.py`:

- `build_metrics_batch_command(...)`
- `build_status_batch_command(...)`
- small helpers for framing one logical section

Keep these builders shell-only. Do not depend on Python being present on the remote hosts.

- [ ] **Step 4: Re-run the targeted builder tests**

Run: `uv run pytest tests/dashboard/test_batch_protocol.py -k "metrics or status" -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/dashboard/test_batch_protocol.py src/server_monitor/dashboard/batch_protocol.py
git commit -m "feat: add batched metrics and status command builders"
```

## Chunk 2: Runtime Batching

### Task 3: Add failing runtime tests for metrics batching

**Files:**
- Modify: `tests/dashboard/test_runtime.py`
- Modify: `src/server_monitor/dashboard/runtime.py`

- [ ] **Step 1: Write failing runtime tests for metrics batching**

Add tests that verify:

- one executor call is made for `system` and `gpu` together on a poll
- system and GPU caches still update independently
- command health still exposes separate summaries for the two cards

Use a fake executor that returns one batched payload containing system and GPU sections.

- [ ] **Step 2: Run the targeted runtime tests to verify RED**

Run: `uv run pytest tests/dashboard/test_runtime.py -k "metrics_batch" -q`

Expected: FAIL because runtime still issues separate SSH commands.

- [ ] **Step 3: Implement minimal metrics batching in the runtime**

In `src/server_monitor/dashboard/runtime.py`:

- add a metrics batch execution path
- parse logical sections from the batch output
- route section payloads through existing system and GPU parsers
- record logical command health for `system` and `gpu`

Do not add persistent-session transport yet.

- [ ] **Step 4: Re-run the metrics batching tests**

Run: `uv run pytest tests/dashboard/test_runtime.py -k "metrics_batch" -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/dashboard/test_runtime.py src/server_monitor/dashboard/runtime.py
git commit -m "feat: batch dashboard metrics polling per server"
```

### Task 4: Add failing runtime tests for status batching and failure isolation

**Files:**
- Modify: `tests/dashboard/test_runtime.py`
- Modify: `src/server_monitor/dashboard/runtime.py`

- [ ] **Step 1: Write failing runtime tests for status batching**

Add tests that verify:

- one executor call is made for all repo git checks plus clash checks on a status poll
- one repo can fail while another repo succeeds within the same batch
- clash secret failure preserves the previous clash snapshot
- repo freshness and command health still behave correctly

- [ ] **Step 2: Run the targeted runtime tests to verify RED**

Run: `uv run pytest tests/dashboard/test_runtime.py -k "status_batch or repo_failure_isolation" -q`

Expected: FAIL because runtime still polls each repo and clash command separately.

- [ ] **Step 3: Implement minimal status batching in the runtime**

In `src/server_monitor/dashboard/runtime.py`:

- build one status batch per server
- parse repo, clash secret, and clash probe sections
- update repo cache entries independently
- preserve current cache fallback semantics
- keep logical command-health records per repo and clash command

- [ ] **Step 4: Re-run the targeted runtime tests**

Run: `uv run pytest tests/dashboard/test_runtime.py -k "status_batch or repo_failure_isolation" -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/dashboard/test_runtime.py src/server_monitor/dashboard/runtime.py
git commit -m "feat: batch dashboard status polling per server"
```

## Chunk 3: Persistent SSH Sessions

### Task 5: Add failing tests for persistent session lifecycle and fallback

**Files:**
- Create: `tests/dashboard/test_persistent_session.py`
- Create: `src/server_monitor/dashboard/persistent_session.py`
- Modify: `src/server_monitor/dashboard/command_runner.py`

- [ ] **Step 1: Write failing persistent-session tests**

Create `tests/dashboard/test_persistent_session.py` with tests that verify:

- a session starts lazily on first use
- a second request on the same alias reuses the existing session
- timeout or EOF kills the session and recreates it on the next request
- malformed completion framing raises a protocol error

- [ ] **Step 2: Run the session tests to verify RED**

Run: `uv run pytest tests/dashboard/test_persistent_session.py -q`

Expected: FAIL with import errors because `persistent_session.py` does not exist yet.

- [ ] **Step 3: Implement the minimal persistent-session transport**

Create `src/server_monitor/dashboard/persistent_session.py` with:

- one session object per alias
- lazy `ssh <alias> sh` startup
- framed request helper
- completion-marker reader
- restart logic on timeout, EOF, or malformed framing

Keep the API narrow and executor-shaped.

- [ ] **Step 4: Re-run the session tests**

Run: `uv run pytest tests/dashboard/test_persistent_session.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/dashboard/test_persistent_session.py src/server_monitor/dashboard/persistent_session.py src/server_monitor/dashboard/command_runner.py
git commit -m "feat: add persistent ssh session transport for dashboard polling"
```

### Task 6: Wire persistent sessions into runtime transport with fallback and docs

**Files:**
- Modify: `src/server_monitor/dashboard/main.py`
- Modify: `src/server_monitor/dashboard/runtime.py`
- Modify: `tests/dashboard/test_runtime.py`
- Modify: `README.md`

- [ ] **Step 1: Add failing integration tests for transport fallback**

Extend `tests/dashboard/test_runtime.py` with tests that verify:

- the runtime prefers the persistent transport when healthy
- a persistent-session failure retries through one-shot SSH for the same poll
- later polls can recreate the persistent session

- [ ] **Step 2: Run the targeted integration tests to verify RED**

Run: `uv run pytest tests/dashboard/test_runtime.py -k "persistent_transport" -q`

Expected: FAIL because runtime does not yet know about the persistent transport.

- [ ] **Step 3: Implement runtime transport selection and fallback**

In `src/server_monitor/dashboard/runtime.py` and `src/server_monitor/dashboard/main.py`:

- instantiate the transport stack
- prefer persistent sessions for batched commands
- fall back to one-shot SSH automatically on transport failure
- keep the caller-facing executor API stable

Update `README.md` with:

- the new transport strategy
- the batching-first sequencing
- a short verification workflow using `/api/diagnostics`

- [ ] **Step 4: Re-run targeted integration tests**

Run: `uv run pytest tests/dashboard/test_runtime.py -k "persistent_transport" -q`

Expected: PASS.

- [ ] **Step 5: Run the full dashboard test slice**

Run: `uv run pytest tests/dashboard/test_batch_protocol.py tests/dashboard/test_persistent_session.py tests/dashboard/test_runtime.py tests/dashboard/test_command_policy.py -q`

Expected: PASS.

- [ ] **Step 6: Live-verify the dashboard latency improvement**

Run:

```bash
powershell -ExecutionPolicy Bypass -File scripts/start-dashboard.ps1
curl http://127.0.0.1:8080/api/diagnostics
```

Expected:

- dashboard starts successfully
- diagnostics endpoint returns `200`
- metrics and status cards show lower latency than the current one-shot baseline

- [ ] **Step 7: Commit**

```bash
git add src/server_monitor/dashboard/main.py src/server_monitor/dashboard/runtime.py tests/dashboard/test_runtime.py README.md
git commit -m "feat: reuse persistent ssh sessions for dashboard polling"
```

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-03-12-v13-dashboard-transport-latency.md`. Ready to execute?
