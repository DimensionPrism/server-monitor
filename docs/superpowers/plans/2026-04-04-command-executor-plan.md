# Extract CommandExecutor - Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract `CommandExecutor` class from `DashboardRuntime` into its own `command_executor.py` module.

**Architecture:** Move `_execute_with_policy`, `_record_batch_failure`, `_record_batch_section_outcome` methods and their data classes (`_PolicyExecutionOutcome`, `_SkippedCommandResult`) into a new `CommandExecutor` class. `DashboardRuntime` delegates to `self._cmd_exec`.

**Tech Stack:** Python 3.12+, pytest, no new dependencies.

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `src/server_monitor/dashboard/command_executor.py` | CommandExecutor class |
| Modify | `src/server_monitor/dashboard/runtime.py` | Add delegation to CommandExecutor |
| Modify | `src/server_monitor/dashboard/status_poller.py` | Update calls from `self._runtime._execute_with_policy` to `self._runtime._cmd_exec.execute_with_policy` |

---

## Task 1: Extract CommandExecutor

**Files:**
- Create: `src/server_monitor/dashboard/command_executor.py`
- Modify: `src/server_monitor/dashboard/runtime.py`
- Modify: `src/server_monitor/dashboard/status_poller.py`

**Source code to extract from `runtime.py`:**
- `_PolicyExecutionOutcome` dataclass (line 49)
- `_SkippedCommandResult` dataclass (line 60)
- `_execute_with_policy` method body (line 650)
- `_record_batch_failure` method body (line 824)
- `_record_batch_section_outcome` method body (line 879)

- [ ] **Step 1: Read source methods in runtime.py**

Read `runtime.py` lines 49-68 (dataclasses), 650-825 (_execute_with_policy), 824-878 (_record_batch_failure), 879-980 (_record_batch_section_outcome).

- [ ] **Step 2: Create command_executor.py**

Create `src/server_monitor/dashboard/command_executor.py` with:
```python
"""Command execution with retry policy extracted from runtime.py."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from types import SimpleNamespace
import time

from server_monitor.dashboard.command_policy import CommandHealthRecord, CommandKind, CommandPolicy
from server_monitor.dashboard.runtime_helpers import _is_ssh_unreachable, _should_retry


@dataclass(slots=True)
class _PolicyExecutionOutcome:
    result: object
    parsed: object | None
    failure_class: str
    attempt_count: int
    message: str
    had_host_unreachable: bool = False
    host_unreachable_message: str = ""


@dataclass(slots=True)
class _SkippedCommandResult:
    stdout: str = ""
    stderr: str = ""
    exit_code: int = -1
    error: str | None = "cooldown_skip"


class CommandExecutor:
    def __init__(self, runtime) -> None:
        self._runtime = runtime

    async def execute_with_policy(
        self,
        *,
        server_id: str,
        ssh_alias: str,
        command_kind: CommandKind,
        target_label: str,
        remote_command: str,
        policy: CommandPolicy,
        parse_output=None,
        cache_used: bool,
    ) -> _PolicyExecutionOutcome:
        # COPY VERBATIM from runtime.py lines 662-819
        # Change: self._run_executor -> self._runtime._run_executor
        # Change: self._failure_tracker_for -> self._runtime._health.failure_tracker_for
        # Change: self._append_command_health -> self._runtime._health.append_command_health
        pass

    def record_batch_failure(
        self,
        *,
        server_id: str,
        command_kind: CommandKind,
        target_label: str,
        result,
        policy: CommandPolicy,
        cache_used: bool,
    ) -> _PolicyExecutionOutcome:
        # COPY VERBATIM from runtime.py lines 824-878
        # Change: self._failure_tracker_for -> self._runtime._health.failure_tracker_for
        # Change: self._append_command_health -> self._runtime._health.append_command_health
        pass

    def record_batch_section_outcome(
        self,
        *,
        server_id: str,
        command_kind: CommandKind,
        target_label: str,
        section_group: dict[str, object] | None,
        policy: CommandPolicy,
        parse_output,
        cache_used: bool,
        fallback_duration_ms: int,
    ) -> _PolicyExecutionOutcome:
        # COPY VERBATIM from runtime.py lines 879-980
        # Change: self._failure_tracker_for -> self._runtime._health.failure_tracker_for
        # Change: self._append_command_health -> self._runtime._health.append_command_health
        pass
```

Copy the method bodies VERBATIM from runtime.py, changing:
- `self.` access to `DashboardRuntime` state → `self._runtime.`
- `self._run_executor(...)` → `self._runtime._run_executor(...)`
- `self._failure_tracker_for(...)` → `self._runtime._health.failure_tracker_for(...)`
- `self._append_command_health(...)` → `self._runtime._health.append_command_health(...)`

- [ ] **Step 3: Wire CommandExecutor into DashboardRuntime**

In `runtime.py` `__init__`:
1. Add import: `from server_monitor.dashboard.command_executor import CommandExecutor`
2. Add: `self._cmd_exec = CommandExecutor(self)`

In `runtime.py`, replace `_execute_with_policy` body with delegate:
```python
async def _execute_with_policy(
    self,
    *,
    server_id: str,
    ssh_alias: str,
    command_kind: CommandKind,
    target_label: str,
    remote_command: str,
    policy: CommandPolicy,
    parse_output=None,
    cache_used: bool,
) -> _PolicyExecutionOutcome:
    return await self._cmd_exec.execute_with_policy(
        server_id=server_id,
        ssh_alias=ssh_alias,
        command_kind=command_kind,
        target_label=target_label,
        remote_command=remote_command,
        policy=policy,
        parse_output=parse_output,
        cache_used=cache_used,
    )
```

Similarly replace `_record_batch_failure` and `_record_batch_section_outcome` with thin delegates.

- [ ] **Step 4: Update status_poller.py calls**

In `status_poller.py`, update calls to `self._runtime._execute_with_policy` to use `self._runtime._cmd_exec.execute_with_policy`.

Similarly update any calls to `_record_batch_failure` or `_record_batch_section_outcome`.

- [ ] **Step 5: Run tests**

Run: `uv run pytest -q`
Expected: All PASS

- [ ] **Step 6: Run lint**

Run: `uv run ruff check src/server_monitor/dashboard/`
Expected: Clean

- [ ] **Step 7: Commit**

```bash
git add src/server_monitor/dashboard/command_executor.py src/server_monitor/dashboard/runtime.py src/server_monitor/dashboard/status_poller.py
git commit -m "refactor: extract CommandExecutor class from DashboardRuntime"
```

---

## Verification Checklist

- [ ] `command_executor.py` created with `CommandExecutor` class
- [ ] `_PolicyExecutionOutcome` and `_SkippedCommandResult` moved to command_executor.py
- [ ] `DashboardRuntime` has `self._cmd_exec = CommandExecutor(self)`
- [ ] `_execute_with_policy`, `_record_batch_failure`, `_record_batch_section_outcome` are thin delegates
- [ ] `status_poller.py` updated to use `self._runtime._cmd_exec.execute_with_policy`
- [ ] All tests pass
- [ ] Lint clean
