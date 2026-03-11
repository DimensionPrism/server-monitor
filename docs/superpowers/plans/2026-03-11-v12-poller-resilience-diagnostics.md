# v1.2 Poller Resilience and Diagnostics Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add bounded retry and cooldown behavior to the agentless poller, then expose a redaction-safe diagnostics bundle built from recent command health records.

**Architecture:** Introduce a focused command policy module and a small in-memory health journal instead of expanding `runtime.py` into an ad hoc retry state machine. The runtime remains the orchestrator, routes remote commands through the policy wrapper, preserves cache/freshness behavior, and exposes recent execution evidence through a diagnostics API endpoint.

**Tech Stack:** Python 3.12, FastAPI, dataclasses, existing SSH command runner, pytest, ruff.

---

## File Structure

- Create: `src/server_monitor/dashboard/command_policy.py`
  - Define command kinds, policy defaults, failure classification, backoff helpers, cooldown bookkeeping, and redaction-safe journal record types.
- Modify: `src/server_monitor/dashboard/runtime.py`
  - Route remote commands through policy execution, maintain cooldown state, append health records, and expose diagnostics bundle data.
- Modify: `src/server_monitor/dashboard/api.py`
  - Add diagnostics endpoint and runtime capability checks.
- Create: `tests/dashboard/test_command_policy.py`
  - Focused policy and redaction unit tests.
- Modify: `tests/dashboard/test_runtime.py`
  - Runtime retry, cooldown, cache-preservation, and health-journal tests.
- Create: `tests/dashboard/test_diagnostics_api.py`
  - Diagnostics endpoint behavior and redaction tests.
- Modify: `README.md`
  - Document the diagnostics endpoint and the resilience-first behavior at a high level.

## Chunk 1: Policy Primitives

### Task 1: Add failing tests for policy classification, cooldown, and redaction

**Files:**
- Create: `tests/dashboard/test_command_policy.py`
- Create: `src/server_monitor/dashboard/command_policy.py`

- [ ] **Step 1: Write the failing policy tests**

Create `tests/dashboard/test_command_policy.py` with tests like:

```python
from server_monitor.dashboard.command_policy import (
    CommandKind,
    classify_failure,
    default_command_policies,
    redact_sensitive_text,
)


def test_timeout_is_retryable_for_system_policy():
    policies = default_command_policies()
    policy = policies[CommandKind.SYSTEM]

    assert policy.retry_on_timeout is True
    assert policy.max_attempts == 2


def test_parse_error_is_not_retryable():
    assert classify_failure(error="parse_error", stderr="") == "parse_error"


def test_redact_sensitive_text_masks_bearer_secret():
    text = "Authorization: Bearer mysecret"
    assert "mysecret" not in redact_sensitive_text(text)
```

- [ ] **Step 2: Run the policy tests to verify RED**

Run: `uv run pytest tests/dashboard/test_command_policy.py -q`

Expected: FAIL with import errors because `command_policy.py` does not exist yet.

- [ ] **Step 3: Implement the minimal policy module**

Create `src/server_monitor/dashboard/command_policy.py` with:

```python
from dataclasses import dataclass
from enum import StrEnum


class CommandKind(StrEnum):
    SYSTEM = "system"
    GPU = "gpu"
    GIT_STATUS = "git_status"
    CLASH_SECRET = "clash_secret"
    CLASH_PROBE = "clash_probe"
    GIT_OPERATION = "git_operation"


@dataclass(frozen=True, slots=True)
class CommandPolicy:
    timeout_seconds: float
    max_attempts: int
    base_backoff_seconds: float
    retry_on_timeout: bool = True
    retry_on_ssh_error: bool = True
    retry_on_nonzero_exit: bool = False
    cooldown_after_failures: int = 3
    cooldown_seconds: float = 15.0
```

Also add:

- `default_command_policies()`
- `classify_failure(...)`
- `redact_sensitive_text(...)`

- [ ] **Step 4: Re-run the policy tests**

Run: `uv run pytest tests/dashboard/test_command_policy.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/dashboard/test_command_policy.py src/server_monitor/dashboard/command_policy.py
git commit -m "feat: add command policy primitives for dashboard polling"
```

### Task 2: Add cooldown bookkeeping and journal record tests

**Files:**
- Modify: `tests/dashboard/test_command_policy.py`
- Modify: `src/server_monitor/dashboard/command_policy.py`

- [ ] **Step 1: Add failing tests for cooldown and health records**

Extend `tests/dashboard/test_command_policy.py` with tests like:

```python
def test_failure_streak_triggers_cooldown_after_threshold():
    tracker = FailureTracker(cooldown_after_failures=2, cooldown_seconds=10.0)
    assert tracker.record_failure(now=10.0) is False
    assert tracker.record_failure(now=12.0) is True


def test_command_health_record_omits_raw_command_text():
    record = CommandHealthRecord(
        server_id="srv-a",
        command_kind=CommandKind.CLASH_PROBE,
        target_label="server",
        message="Authorization: Bearer mysecret",
    )
    assert "mysecret" not in record.message
```

- [ ] **Step 2: Run targeted tests to verify RED**

Run: `uv run pytest tests/dashboard/test_command_policy.py -k "cooldown or record" -q`

Expected: FAIL because the tracker and record helpers do not exist yet.

- [ ] **Step 3: Implement minimal cooldown and journal primitives**

Add to `src/server_monitor/dashboard/command_policy.py`:

- `FailureTracker`
- `CommandHealthRecord`
- helper for creating redacted records

Keep the module focused. Do not put runtime orchestration logic here.

- [ ] **Step 4: Re-run the targeted tests**

Run: `uv run pytest tests/dashboard/test_command_policy.py -k "cooldown or record" -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/dashboard/test_command_policy.py src/server_monitor/dashboard/command_policy.py
git commit -m "feat: add cooldown tracking and health record helpers"
```

## Chunk 2: Runtime Resilience Integration

### Task 3: Add failing runtime tests for retry success and fail-fast parse behavior

**Files:**
- Modify: `tests/dashboard/test_runtime.py`
- Modify: `src/server_monitor/dashboard/runtime.py`

- [ ] **Step 1: Write failing runtime tests**

Add tests in `tests/dashboard/test_runtime.py` for:

```python
@pytest.mark.asyncio
async def test_runtime_retries_system_timeout_once_before_success():
    ...
    assert payload["snapshot"]["cpu_percent"] == 11.0
    assert health["attempt_count"] == 2
    assert health["failure_class"] == "ok"


@pytest.mark.asyncio
async def test_runtime_does_not_retry_parse_failure():
    ...
    assert health["attempt_count"] == 1
    assert health["failure_class"] == "parse_error"
```

Use executor doubles that fail once with timeout, then succeed, and a parser failure path that should stop immediately.

- [ ] **Step 2: Run targeted runtime tests to verify RED**

Run: `uv run pytest tests/dashboard/test_runtime.py -k "retries_system_timeout_once_before_success or does_not_retry_parse_failure" -q`

Expected: FAIL because runtime does not expose policy-driven attempts or command health yet.

- [ ] **Step 3: Implement minimal runtime policy wrapper**

In `src/server_monitor/dashboard/runtime.py`:

- import policy helpers from `command_policy.py`
- add runtime-owned policy table
- add wrapper such as:

```python
async def _execute_with_policy(
    self,
    *,
    server_id: str,
    command_kind: CommandKind,
    target_label: str,
    remote_command: str,
    policy: CommandPolicy,
):
    ...
```

- use it for `system`, `gpu`, `git_status`, `clash_secret`, and `clash_probe`

Keep current cache update logic intact.

- [ ] **Step 4: Re-run the targeted runtime tests**

Run: `uv run pytest tests/dashboard/test_runtime.py -k "retries_system_timeout_once_before_success or does_not_retry_parse_failure" -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/dashboard/test_runtime.py src/server_monitor/dashboard/runtime.py
git commit -m "feat: add policy-driven retry execution to dashboard runtime"
```

### Task 4: Add failing runtime tests for cooldown and cache preservation

**Files:**
- Modify: `tests/dashboard/test_runtime.py`
- Modify: `src/server_monitor/dashboard/runtime.py`

- [ ] **Step 1: Write failing cooldown and cache tests**

Add tests covering:

```python
@pytest.mark.asyncio
async def test_runtime_applies_cooldown_after_repeated_clash_secret_failures():
    ...
    assert latest_health["failure_class"] == "cooldown_skip"


@pytest.mark.asyncio
async def test_runtime_keeps_cached_git_repo_during_cooldown():
    ...
    assert payload["repos"][0]["path"] == "/work/repo-a"
```

Use a fake executor that repeatedly times out for one target so the next cycle should skip immediate reattempt.

- [ ] **Step 2: Run targeted runtime tests to verify RED**

Run: `uv run pytest tests/dashboard/test_runtime.py -k "cooldown" -q`

Expected: FAIL because cooldown state is not implemented.

- [ ] **Step 3: Implement minimal cooldown state and journaling**

In `src/server_monitor/dashboard/runtime.py`:

- add per-target failure tracker storage
- add recent health journal storage with bounded retention
- write one journal record per wrapped execution
- emit `cooldown_skip` records when a target is temporarily suppressed

Do not change websocket payload shape for monitor cards in this task.

- [ ] **Step 4: Re-run cooldown-focused runtime tests**

Run: `uv run pytest tests/dashboard/test_runtime.py -k "cooldown" -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/dashboard/test_runtime.py src/server_monitor/dashboard/runtime.py
git commit -m "feat: add cooldown and command health journal to runtime"
```

## Chunk 3: Diagnostics Export

### Task 5: Add failing API tests for diagnostics export and redaction

**Files:**
- Create: `tests/dashboard/test_diagnostics_api.py`
- Modify: `src/server_monitor/dashboard/api.py`
- Modify: `src/server_monitor/dashboard/runtime.py`

- [ ] **Step 1: Write failing diagnostics API tests**

Create `tests/dashboard/test_diagnostics_api.py` with tests like:

```python
from fastapi.testclient import TestClient


def test_diagnostics_endpoint_returns_empty_bundle_when_no_records(tmp_path):
    ...
    response = client.get("/api/diagnostics")
    assert response.status_code == 200
    assert response.json()["servers"] == []


def test_diagnostics_endpoint_redacts_clash_secret(tmp_path):
    ...
    bundle = client.get("/api/diagnostics").json()
    assert "mysecret" not in str(bundle)
```

Also add a test for `503` when runtime support is absent.

- [ ] **Step 2: Run diagnostics API tests to verify RED**

Run: `uv run pytest tests/dashboard/test_diagnostics_api.py -q`

Expected: FAIL because `/api/diagnostics` does not exist yet.

- [ ] **Step 3: Implement diagnostics bundle builder and route**

In `src/server_monitor/dashboard/runtime.py`, add a method such as:

```python
def build_diagnostics_bundle(self) -> dict:
    ...
```

Include:

- generated timestamp
- serialized settings
- recent command records grouped by server and target
- summary fields like success count, failure count, average duration, last failure class

In `src/server_monitor/dashboard/api.py`:

- add `_require_diagnostics_runtime(...)`
- add `GET /api/diagnostics`

Return redaction-safe JSON only.

- [ ] **Step 4: Re-run diagnostics API tests**

Run: `uv run pytest tests/dashboard/test_diagnostics_api.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/dashboard/test_diagnostics_api.py src/server_monitor/dashboard/api.py src/server_monitor/dashboard/runtime.py
git commit -m "feat: add diagnostics export endpoint for dashboard runtime"
```

## Chunk 4: Documentation and Verification

### Task 6: Document the new diagnostics flow and run verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add failing documentation-aware assertion if useful**

Optional lightweight test:

```python
def test_readme_mentions_diagnostics_endpoint():
    text = Path("README.md").read_text(encoding="utf-8")
    assert "/api/diagnostics" in text
```

If this adds more noise than value, skip the test and document directly.

- [ ] **Step 2: Update README**

Add concise documentation for:

- bounded retries and cooldown behavior
- diagnostics export endpoint
- the fact that the bundle is redaction-safe and JSON-based

- [ ] **Step 3: Run focused regression suites**

Run:

```bash
uv run pytest tests/dashboard/test_command_policy.py tests/dashboard/test_runtime.py tests/dashboard/test_diagnostics_api.py tests/dashboard/test_settings_api.py -q
```

Expected: PASS.

- [ ] **Step 4: Run full verification**

Run:

```bash
uv run pytest -q
uv run ruff check .
```

Expected: PASS for both commands.

- [ ] **Step 5: Commit**

```bash
git add README.md tests/dashboard/test_command_policy.py tests/dashboard/test_runtime.py tests/dashboard/test_diagnostics_api.py src/server_monitor/dashboard/command_policy.py src/server_monitor/dashboard/runtime.py src/server_monitor/dashboard/api.py
git commit -m "feat: harden dashboard polling and add diagnostics export"
```

Plan complete and saved to `docs/superpowers/plans/2026-03-11-v12-poller-resilience-diagnostics.md`. Ready to execute?
