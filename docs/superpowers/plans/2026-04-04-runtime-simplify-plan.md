# runtime.py Simplification - Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split `runtime.py` (2185 lines, 37 top-level definitions) into focused modules by responsibility.

**Architecture:** Extract domain-specific methods into dedicated modules (`status_poller.py`, `git_operations.py`, `command_health.py`), move standalone pure functions to `runtime_helpers.py`, keep `DashboardRuntime` as thin orchestrator.

**Tech Stack:** Python 3.12+, pytest, no new dependencies.

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Modify | `src/server_monitor/dashboard/runtime.py` | Thin orchestrator; retains `DashboardRuntime`, `SshCommandExecutor`, dataclasses, `__init__` |
| Create | `src/server_monitor/dashboard/runtime_helpers.py` | All standalone pure functions |
| Create | `src/server_monitor/dashboard/status_poller.py` | Status polling (metrics, panels), poll task management |
| Create | `src/server_monitor/dashboard/git_operations.py` | Git polling and operations |
| Create | `src/server_monitor/dashboard/command_health.py` | Health tracking, summaries, failure classification |
| Modify | `tests/dashboard/test_runtime.py` | Move helper function tests to new test file |

---

## Module Boundaries

### runtime_helpers.py
Pure standalone functions moved verbatim from `runtime.py` lines 1671-2185:
- Command builders: `_system_command()`, `_gpu_command()`, `_git_status_command()`, `_git_operation_command()`, `_clash_command()`, `_batched_clash_secret_command()`, `_batched_clash_probe_command()`
- Serializers: `_serialize_runtime_settings()`, `_serialize_metrics_stream_status()`, `_metrics_stream_status_for()`
- Utilities: `_needs_status_poll()`, `_metrics_sleep_seconds()`, `_is_ssh_unreachable()`, `_shell_quote()`, `_group_batch_sections()`, `_find_server()`, `_should_retry()`, `_build_freshness_entry()`, `_age_seconds_from_iso()`, `_metrics_stream_transport_latency_ms()`, `_metrics_stream_latency_upper_bound_ms()`, `_extract_clash_secret()`, `_parse_required_clash_secret()`, `_is_valid_branch_name()`
- Empty data: `_empty_repo_status()`, `_empty_system_snapshot()`

### status_poller.py
Owns all status polling logic from `DashboardRuntime`:
- `_poll_metrics()`, `_poll_metrics_batch()`
- `_poll_status_panels()`
- `_is_status_poll_inflight()`, `_consume_finished_status_poll_task()`, `_consume_status_poll_task_result()`
- `_start_status_poll_if_needed()`
- `_build_cached_snapshot()`

### git_operations.py
Owns git polling and operations from `DashboardRuntime`:
- `_poll_git_repos()`, `_poll_single_git_repo()`
- `_run_git_operation_command()`
- `_replace_cached_repo()`
- `_empty_repo_status()`

### command_health.py
Owns health tracking from `DashboardRuntime`:
- `_append_command_health()`, `_failure_tracker_for()`
- `_summarize_server_command_health()`, `_latest_command_health_record()`
- `_summary_for_metrics_stream()`, `_summary_for_single_command()`, `_summary_for_git()`, `_summary_for_clash()`
- All `_command_health_*` module-level helpers (lines 1683-1765)

### runtime.py (after refactor)
Retains:
- `SshCommandExecutor` (unchanged, lines 83-96)
- `DashboardRuntime` class (delegates to submodules; target ~450 lines)
- Dataclasses: `_MetricsStreamStatus` (lines 72-81), `_PolicyExecutionOutcome` (lines 53-60), `_SkippedCommandResult` (lines 64-68)
- Constants moved to `runtime_helpers.py`

---

## Task 1: Create runtime_helpers.py

**Files:**
- Create: `src/server_monitor/dashboard/runtime_helpers.py`
- Modify: `src/server_monitor/dashboard/runtime.py`
- Test: Create `tests/dashboard/test_runtime_helpers.py`

**Source lines to extract:** runtime.py lines 1671-2185 (module-level functions)

- [ ] **Step 1: Create runtime_helpers.py**

Copy ALL module-level functions and constants from runtime.py (lines 38-49 and 1671-2185) into a new file `runtime_helpers.py` with:
- Module docstring: `"""Pure helper functions extracted from runtime.py."""`
- `from __future__ import annotations`
- No imports from other dashboard modules (all imports are stdlib or already in runtime_helpers)

Functions to copy verbatim:
```python
# Constants (from lines 38-49)
DEFAULT_CLASH = {...}
GIT_OPERATION_TIMEOUT_SECONDS = 20.0
STATUS_COMMAND_TIMEOUT_SECONDS = 3.0
STATUS_POLL_INLINE_BUDGET_SECONDS = 0.05
COMMAND_HEALTH_HISTORY_LIMIT = 20

# Helper functions (from lines 1671-2185)
def _needs_status_poll(...): ...
def _metrics_sleep_seconds(...): ...
def _unknown_command_health_summary(...): ...
def _command_health_summary_from_record(...): ...
def _command_health_state_from_record(...): ...
def _command_health_label(...): ...
def _command_health_severity(...): ...
def _worst_command_health_state(...): ...
def _git_command_health_detail(...): ...
def _find_server(...): ...
def _serialize_runtime_settings(...): ...
def _is_ssh_unreachable(...): ...
def _shell_quote(...): ...
def _group_batch_sections(...): ...
def _empty_repo_status(...): ...
def _empty_system_snapshot(...): ...
def _system_command(): ...
def _gpu_command(): ...
def _git_status_command(...): ...
def _git_operation_command(...): ...
def _is_valid_branch_name(...): ...
def _should_retry(...): ...
def _build_freshness_entry(...): ...
def _age_seconds_from_iso(...): ...
def _metrics_stream_transport_latency_ms(...): ...
def _metrics_stream_latency_upper_bound_ms(...): ...
def _extract_clash_secret(...): ...
def _parse_required_clash_secret(...): ...
def _batched_clash_secret_command(): ...
def _clash_secret_command(): ...
def _batched_clash_probe_command(...): ...
def _clash_command(...): ...
```

- [ ] **Step 2: Update runtime.py imports and remove moved code**

In runtime.py `__init__` block, remove the moved functions and add import:
```python
from server_monitor.dashboard.runtime_helpers import (
    DEFAULT_CLASH,
    GIT_OPERATION_TIMEOUT_SECONDS,
    STATUS_COMMAND_TIMEOUT_SECONDS,
    STATUS_POLL_INLINE_BUDGET_SECONDS,
    COMMAND_HEALTH_HISTORY_LIMIT,
    _needs_status_poll,
    _metrics_sleep_seconds,
    _system_command,
    _gpu_command,
    _git_status_command,
    _git_operation_command,
    _clash_secret_command,
    _clash_command,
    _batched_clash_secret_command,
    _batched_clash_probe_command,
    _serialize_runtime_settings,
    _serialize_metrics_stream_status,
    _metrics_stream_status_for,
    _is_ssh_unreachable,
    _shell_quote,
    _group_batch_sections,
    _find_server,
    _should_retry,
    _build_freshness_entry,
    _age_seconds_from_iso,
    _metrics_stream_transport_latency_ms,
    _metrics_stream_latency_upper_bound_ms,
    _extract_clash_secret,
    _parse_required_clash_secret,
    _is_valid_branch_name,
    _empty_repo_status,
    _empty_system_snapshot,
    _unknown_command_health_summary,
    _command_health_summary_from_record,
    _command_health_state_from_record,
    _command_health_label,
    _command_health_severity,
    _worst_command_health_state,
    _git_command_health_detail,
)
```

Then delete all the moved function bodies (lines 38-49 constants and lines 1671-2185).

- [ ] **Step 3: Create test_runtime_helpers.py**

Move tests from `test_runtime.py` (lines 2029-2810) to a new file `tests/dashboard/test_runtime_helpers.py`:
- `test_metrics_sleep_seconds_compensates_poll_time` (line 2029)
- `test_batched_clash_secret_command_runs_lookup_in_child_shell` (line 2036)
- `test_extract_clash_secret_parses_chinese_label_output` (line 2275)
- `test_clash_secret_command_includes_runtime_yaml_fallback` (line 2282)
- `test_clash_command_includes_bearer_header_for_api_and_ui` (line 2291)
- `test_clash_command_routes_ip_lookup_via_detected_proxy_port` (line 2308)
- `test_clash_command_parses_ip_lookup_fields_in_provider_order` (line 2322)
- `test_metrics_stream_transport_latency_rejects_clock_skew_and_implausible_outliers` (line 2810)

Update imports in the new test file to use `runtime_helpers` instead of `runtime`.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/dashboard/test_runtime_helpers.py -v`
Expected: All 8 tests PASS

Run: `uv run pytest -q`
Expected: All PASS (no new failures)

- [ ] **Step 5: Commit**

```bash
git add src/server_monitor/dashboard/runtime_helpers.py tests/dashboard/test_runtime_helpers.py src/server_monitor/dashboard/runtime.py
git commit -m "refactor: extract runtime_helpers.py with pure functions"
```

---

## Task 2: Create status_poller.py

**Files:**
- Create: `src/server_monitor/dashboard/status_poller.py`
- Modify: `src/server_monitor/dashboard/runtime.py`

**Source:** Extract methods from `DashboardRuntime` in runtime.py

- [ ] **Step 1: Create status_poller.py with StatusPoller class**

Create a new file `status_poller.py` containing:

```python
"""Status polling logic extracted from runtime.py."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import UTC, datetime
from types import SimpleNamespace

from server_monitor.dashboard.batch_protocol import (
    BatchProtocolError,
    build_metrics_batch_command,
    parse_batch_output,
)
from server_monitor.dashboard.command_policy import CommandKind, CommandPolicy
from server_monitor.dashboard.parsers.clash import parse_clash_status
from server_monitor.dashboard.parsers.git_status import parse_repo_status
from server_monitor.dashboard.parsers.gpu import parse_gpu_snapshot
from server_monitor.dashboard.parsers.system import parse_system_snapshot
from server_monitor.dashboard.runtime_helpers import (
    DEFAULT_CLASH,
    STATUS_POLL_INLINE_BUDGET_SECONDS,
    _clash_command,
    _clash_secret_command,
    _batched_clash_secret_command,
    _batched_clash_probe_command,
    _extract_clash_secret,
    _gpu_command,
    _group_batch_sections,
    _is_ssh_unreachable,
    _parse_required_clash_secret,
    _serialize_metrics_stream_status,
    _system_command,
)

class StatusPoller:
    def __init__(self, runtime) -> None:
        self._runtime = runtime
```

Extract these methods from `DashboardRuntime` (copy body verbatim, change `self.` to `self._runtime.`):
- `_is_status_poll_inflight` → `is_status_poll_inflight` (line 568)
- `_consume_finished_status_poll_task` → `consume_finished_status_poll_task` (line 572)
- `_consume_status_poll_task_result` → `_consume_status_poll_task_result` (line 578)
- `_start_status_poll_if_needed` → `start_status_poll_if_needed` (line 589)
- `_poll_status_panels` → `poll_status_panels` (line 611)

- [ ] **Step 2: Wire StatusPoller into DashboardRuntime**

In `runtime.py __init__`, add:
```python
from server_monitor.dashboard.status_poller import StatusPoller
```

Add `self._status_poller = StatusPoller(self)` to `DashboardRuntime.__init__`.

Replace the extracted methods with thin delegates:
```python
def _is_status_poll_inflight(self, server_id: str) -> bool:
    return self._status_poller.is_status_poll_inflight(server_id)

def _consume_finished_status_poll_task(self, server_id: str) -> None:
    return self._status_poller.consume_finished_status_poll_task(server_id)

async def _start_status_poll_if_needed(self, *, server, now: datetime) -> None:
    return await self._status_poller.start_status_poll_if_needed(server=server, now=now)

async def _poll_status_panels(self, *, server, polled_at_iso: str) -> None:
    return await self._status_poller.poll_status_panels(server=server, polled_at_iso=polled_at_iso)
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest -q`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add src/server_monitor/dashboard/status_poller.py src/server_monitor/dashboard/runtime.py
git commit -m "refactor: extract StatusPoller class from DashboardRuntime"
```

---

## Task 3: Create git_operations.py

**Files:**
- Create: `src/server_monitor/dashboard/git_operations.py`
- Modify: `src/server_monitor/dashboard/runtime.py`

- [ ] **Step 1: Create git_operations.py with GitOperations class**

Create `git_operations.py` with class `GitOperations` that wraps:
- `_poll_git_repos` → `poll_git_repos` (line 884)
- `_poll_single_git_repo` → `poll_single_git_repo` (line 922)
- `_run_git_operation_command` → `run_git_operation_command` (line 1038)
- `_replace_cached_repo` → `replace_cached_repo` (line 1656)
- `_empty_repo_status` → `empty_repo_status` (line 1819)

Import `GIT_OPERATION_TIMEOUT_SECONDS` from `runtime_helpers`.

Import from `runtime` via lazy import to avoid circular dependency (or use `TYPE_CHECKING` + string annotation).

- [ ] **Step 2: Wire GitOperations into DashboardRuntime**

Same pattern as Task 2 Step 2.

- [ ] **Step 3: Run tests**

Run: `uv run pytest -q`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add src/server_monitor/dashboard/git_operations.py src/server_monitor/dashboard/runtime.py
git commit -m "refactor: extract GitOperations class from DashboardRuntime"
```

---

## Task 4: Create command_health.py

**Files:**
- Create: `src/server_monitor/dashboard/command_health.py`
- Modify: `src/server_monitor/dashboard/runtime.py`

- [ ] **Step 1: Create command_health.py with CommandHealthTracker class**

Create `command_health.py` with class `CommandHealthTracker` that wraps:
- `_append_command_health` → `append_command_health` (line 1370)
- `_failure_tracker_for` → `failure_tracker_for` (line 1377)
- `_summarize_server_command_health` → `summarize_server_command_health` (line 1395)
- `_latest_command_health_record` → `latest_command_health_record` (line 1552)
- `_summary_for_metrics_stream` → `summary_for_metrics_stream` (line 1427)
- `_summary_for_single_command` → `summary_for_single_command` (line 1467)
- `_summary_for_git` → `summary_for_git` (line 1482)
- `_summary_for_clash` → `summary_for_clash` (line 1527)

Also extract module-level helpers (move from `runtime_helpers.py` or keep in `command_health.py`):
- `_unknown_command_health_summary`
- `_command_health_summary_from_record`
- `_command_health_state_from_record`
- `_command_health_label`
- `_command_health_severity`
- `_worst_command_health_state`
- `_git_command_health_detail`

- [ ] **Step 2: Wire CommandHealthTracker into DashboardRuntime**

Same pattern as Task 2 Step 2.

- [ ] **Step 3: Run tests**

Run: `uv run pytest -q`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add src/server_monitor/dashboard/command_health.py src/server_monitor/dashboard/runtime.py
git commit -m "refactor: extract CommandHealthTracker class from DashboardRuntime"
```

---

## Task 5: Final verification and cleanup

**Files:**
- Modify: `src/server_monitor/dashboard/runtime.py`

- [ ] **Step 1: Verify runtime.py line count**

Target: under 600 lines (currently 2185)

Expected remaining in runtime.py after all extractions:
- ~100 lines: imports + dataclasses + constants
- ~450 lines: DashboardRuntime methods (start, stop, _run_loop, _poll_server, _broadcast_server_state, _poll_metrics, _poll_metrics_batch, _execute_with_policy, _record_batch_failure, _record_batch_section_outcome, _handle_metrics_stream_sample, _handle_metrics_stream_state_change, get_recent_command_health, build_diagnostics_bundle, run_git_operation, open_repo_terminal, _run_executor, _run_batch_executor)

- [ ] **Step 2: Run lint**

Run: `uv run ruff check src/server_monitor/dashboard/`
Expected: Clean (or only pre-existing warnings)

- [ ] **Step 3: Run full test suite**

Run: `uv run pytest -q`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add src/server_monitor/dashboard/runtime.py
git commit -m "refactor: slim down runtime.py after extracting domain modules"
```

---

## Verification Checklist

- [ ] `runtime.py` is under 600 lines
- [ ] Each new module is under 400 lines
- [ ] `uv run ruff check src/server_monitor/dashboard/` passes
- [ ] `uv run pytest -q` passes with no new failures
- [ ] `api.py` imports `runtime.DashboardRuntime` unchanged
- [ ] No circular imports between new modules
