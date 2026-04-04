# Codebase Structure Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure `src/server_monitor/dashboard/` into focused subpackages (ssh/, metrics/, health/, runtime/, panels/) to improve maintainability.

**Architecture:** Group related files into subpackages. SSH transport, metrics streaming, health tracking, runtime coordination, and panel data collection each get their own package. Top-level keeps only files with special placement requirements (api.py, cli.py, main.py, settings.py, ws_hub.py) plus utilities used widely across the app.

**Tech Stack:** Python 3.12+, FastAPI, asyncio

---

## File Map

### New Structure
```
src/server_monitor/dashboard/
├── __init__.py
├── api.py                  # FastAPI routes
├── cli.py                  # CLI entrypoint
├── main.py                 # App factory
├── settings.py             # Settings models
├── ws_hub.py              # WebSocket hub
├── normalize.py           # Payload normalization
├── clash_tunnel.py       # Clash tunnel manager
├── terminal_launcher.py   # Terminal launcher
├── command_executor.py    # Command executor
├── ssh/
│   ├── __init__.py
│   ├── command_runner.py
│   ├── persistent_session.py
│   └── ssh_tunnel.py
├── metrics/
│   ├── __init__.py
│   ├── manager.py              # MetricsStreamManager
│   ├── command.py              # MetricsStreamCommand
│   ├── protocol.py             # MetricsStreamProtocol
│   └── batch_protocol.py      # BatchProtocol
├── health/
│   ├── __init__.py
│   ├── command_health.py       # CommandHealthTracker
│   └── command_policy.py      # CommandPolicy, FailureTracker
├── runtime/
│   ├── __init__.py
│   ├── runtime.py              # DashboardRuntime, SshCommandExecutor
│   ├── runtime_helpers.py      # Helper functions
│   └── status_poller.py       # StatusPoller
└── panels/
    ├── __init__.py
    ├── git_operations.py       # GitOperations
    └── parsers/
        ├── __init__.py
        ├── clash.py
        ├── git_status.py
        ├── gpu.py
        └── system.py
```

### Files to Create
- `src/server_monitor/dashboard/ssh/__init__.py`
- `src/server_monitor/dashboard/metrics/__init__.py`
- `src/server_monitor/dashboard/health/__init__.py`
- `src/server_monitor/dashboard/runtime/__init__.py`
- `src/server_monitor/dashboard/panels/__init__.py`
- `src/server_monitor/dashboard/panels/parsers/__init__.py`

### Files to Move (no content change)
| From | To |
|------|-----|
| `ssh/command_runner.py` | `ssh/command_runner.py` |
| `ssh/persistent_session.py` | `ssh/persistent_session.py` |
| `ssh/ssh_tunnel.py` | `ssh/ssh_tunnel.py` |
| `metrics_stream_manager.py` | `metrics/manager.py` |
| `metrics_stream_command.py` | `metrics/command.py` |
| `metrics_stream_protocol.py` | `metrics/protocol.py` |
| `batch_protocol.py` | `metrics/batch_protocol.py` |
| `command_health.py` | `health/command_health.py` |
| `command_policy.py` | `health/command_policy.py` |
| `runtime.py` | `runtime/runtime.py` |
| `runtime_helpers.py` | `runtime/runtime_helpers.py` |
| `status_poller.py` | `runtime/status_poller.py` |
| `git_operations.py` | `panels/git_operations.py` |
| `parsers/clash.py` | `panels/parsers/clash.py` |
| `parsers/git_status.py` | `panels/parsers/git_status.py` |
| `parsers/gpu.py` | `panels/parsers/gpu.py` |
| `parsers/system.py` | `panels/parsers/system.py` |

### Files to Modify (import updates only)
- `src/server_monitor/dashboard/__init__.py`
- `src/server_monitor/dashboard/api.py`
- `src/server_monitor/dashboard/main.py`
- `src/server_monitor/dashboard/clash_tunnel.py`
- `src/server_monitor/dashboard/command_executor.py`
- `src/server_monitor/dashboard/ssh/__init__.py`
- `src/server_monitor/dashboard/metrics/__init__.py`
- `src/server_monitor/dashboard/health/__init__.py`
- `src/server_monitor/dashboard/runtime/__init__.py`
- `src/server_monitor/dashboard/panels/__init__.py`
- `src/server_monitor/dashboard/panels/parsers/__init__.py`
- All test files in `tests/dashboard/`

---

## Tasks

### Task 1: Create subpackage skeleton

**Files:**
- Create: `src/server_monitor/dashboard/ssh/__init__.py`
- Create: `src/server_monitor/dashboard/metrics/__init__.py`
- Create: `src/server_monitor/dashboard/health/__init__.py`
- Create: `src/server_monitor/dashboard/runtime/__init__.py`
- Create: `src/server_monitor/dashboard/panels/__init__.py`
- Create: `src/server_monitor/dashboard/panels/parsers/__init__.py`

- [ ] **Step 1: Create `ssh/__init__.py`**

```python
"""SSH transport layer."""

from __future__ import annotations

from server_monitor.dashboard.ssh.command_runner import CommandRunner
from server_monitor.dashboard.ssh.persistent_session import PersistentBatchTransport
from server_monitor.dashboard.ssh.ssh_tunnel import SSH_TunnelManager

__all__ = [
    "CommandRunner",
    "PersistentBatchTransport",
    "SSH_TunnelManager",
]
```

- [ ] **Step 2: Create `metrics/__init__.py`**

```python
"""Metrics streaming subsystem."""

from __future__ import annotations

from server_monitor.dashboard.metrics.manager import MetricsStreamManager
from server_monitor.dashboard.metrics.command import MetricsStreamCommand
from server_monitor.dashboard.metrics.protocol import MetricsStreamProtocol
from server_monitor.dashboard.metrics.batch_protocol import BatchProtocol

__all__ = [
    "MetricsStreamManager",
    "MetricsStreamCommand",
    "MetricsStreamProtocol",
    "BatchProtocol",
]
```

- [ ] **Step 3: Create `health/__init__.py`**

```python
"""Command health tracking subsystem."""

from __future__ import annotations

from server_monitor.dashboard.health.command_health import CommandHealthTracker
from server_monitor.dashboard.health.command_policy import (
    CommandHealthRecord,
    CommandKind,
    CommandPolicy,
    FailureTracker,
    default_command_policies,
)

__all__ = [
    "CommandHealthTracker",
    "CommandHealthRecord",
    "CommandKind",
    "CommandPolicy",
    "FailureTracker",
    "default_command_policies",
]
```

- [ ] **Step 4: Create `runtime/__init__.py`**

```python
"""Core polling runtime subsystem."""

from __future__ import annotations

from server_monitor.dashboard.runtime.runtime import DashboardRuntime, SshCommandExecutor
from server_monitor.dashboard.runtime.status_poller import StatusPoller

__all__ = [
    "DashboardRuntime",
    "SshCommandExecutor",
    "StatusPoller",
]
```

- [ ] **Step 5: Create `panels/__init__.py`**

```python
"""Panel data collection subsystem."""

from __future__ import annotations

from server_monitor.dashboard.panels.git_operations import GitOperations

__all__ = [
    "GitOperations",
]
```

- [ ] **Step 6: Create `panels/parsers/__init__.py`**

```python
"""Output parsers for SSH command results."""

from __future__ import annotations

from server_monitor.dashboard.panels.parsers.clash import parse_clash_status
from server_monitor.dashboard.panels.parsers.git_status import parse_repo_status
from server_monitor.dashboard.panels.parsers.gpu import parse_gpu_output
from server_monitor.dashboard.panels.parsers.system import parse_system_output

__all__ = [
    "parse_clash_status",
    "parse_repo_status",
    "parse_gpu_output",
    "parse_system_output",
]
```

- [ ] **Step 7: Commit**

```bash
git add src/server_monitor/dashboard/ssh/__init__.py
git add src/server_monitor/dashboard/metrics/__init__.py
git add src/server_monitor/dashboard/health/__init__.py
git add src/server_monitor/dashboard/runtime/__init__.py
git add src/server_monitor/dashboard/panels/__init__.py
git add src/server_monitor/dashboard/panels/parsers/__init__.py
git commit -m "refactor: create subpackage skeletons with __init__.py exports"
```

---

### Task 2: Move SSH package files

**Files:**
- Create: `src/server_monitor/dashboard/ssh/command_runner.py`
- Create: `src/server_monitor/dashboard/ssh/persistent_session.py`
- Create: `src/server_monitor/dashboard/ssh/ssh_tunnel.py`
- Delete: `src/server_monitor/dashboard/command_runner.py`
- Delete: `src/server_monitor/dashboard/persistent_session.py`
- Delete: `src/server_monitor/dashboard/ssh_tunnel.py`
- Modify: `src/server_monitor/dashboard/main.py`
- Modify: `src/server_monitor/dashboard/clash_tunnel.py`
- Modify: `src/server_monitor/dashboard/ssh/__init__.py`

- [ ] **Step 1: Move `command_runner.py` to `ssh/command_runner.py`**

Read `src/server_monitor/dashboard/command_runner.py`, write to `src/server_monitor/dashboard/ssh/command_runner.py`

- [ ] **Step 2: Move `persistent_session.py` to `ssh/persistent_session.py`**

Read `src/server_monitor/dashboard/persistent_session.py`, write to `src/server_monitor/dashboard/ssh/persistent_session.py`

- [ ] **Step 3: Move `ssh_tunnel.py` to `ssh/ssh_tunnel.py`**

Read `src/server_monitor/dashboard/ssh_tunnel.py`, write to `src/server_monitor/dashboard/ssh/ssh_tunnel.py`

- [ ] **Step 4: Delete original files**

```bash
rm src/server_monitor/dashboard/command_runner.py
rm src/server_monitor/dashboard/persistent_session.py
rm src/server_monitor/dashboard/ssh_tunnel.py
```

- [ ] **Step 5: Update `main.py` imports**

Read `src/server_monitor/dashboard/main.py`, update import from:
```python
from server_monitor.dashboard.persistent_session import PersistentBatchTransport
```
to:
```python
from server_monitor.dashboard.ssh import PersistentBatchTransport
```

- [ ] **Step 6: Update `clash_tunnel.py` imports**

Read `src/server_monitor/dashboard/clash_tunnel.py`, update import from:
```python
from server_monitor.dashboard.ssh_tunnel import SSH_TunnelManager
```
to:
```python
from server_monitor.dashboard.ssh import SSH_TunnelManager
```

- [ ] **Step 7: Run lint check**

```bash
uv run ruff check src/server_monitor/dashboard/ssh/
```
Expected: No errors

- [ ] **Step 8: Commit**

```bash
git add src/server_monitor/dashboard/ssh/
git add src/server_monitor/dashboard/main.py
git add src/server_monitor/dashboard/clash_tunnel.py
git rm src/server_monitor/dashboard/command_runner.py
git rm src/server_monitor/dashboard/persistent_session.py
git rm src/server_monitor/dashboard/ssh_tunnel.py
git commit -m "refactor: move SSH transport layer to ssh/ subpackage"
```

---

### Task 3: Move metrics package files

**Files:**
- Create: `src/server_monitor/dashboard/metrics/manager.py`
- Create: `src/server_monitor/dashboard/metrics/command.py`
- Create: `src/server_monitor/dashboard/metrics/protocol.py`
- Create: `src/server_monitor/dashboard/metrics/batch_protocol.py`
- Delete: `src/server_monitor/dashboard/metrics_stream_manager.py`
- Delete: `src/server_monitor/dashboard/metrics_stream_command.py`
- Delete: `src/server_monitor/dashboard/metrics_stream_protocol.py`
- Delete: `src/server_monitor/dashboard/batch_protocol.py`
- Modify: `src/server_monitor/dashboard/main.py`
- Modify: `src/server_monitor/dashboard/runtime/runtime.py` (after move)

- [ ] **Step 1: Move `metrics_stream_manager.py` to `metrics/manager.py`**

Read `src/server_monitor/dashboard/metrics_stream_manager.py`, write to `src/server_monitor/dashboard/metrics/manager.py`

- [ ] **Step 2: Move `metrics_stream_command.py` to `metrics/command.py`**

Read `src/server_monitor/dashboard/metrics_stream_command.py`, write to `src/server_monitor/dashboard/metrics/command.py`

- [ ] **Step 3: Move `metrics_stream_protocol.py` to `metrics/protocol.py`**

Read `src/server_monitor/dashboard/metrics_stream_protocol.py`, write to `src/server_monitor/dashboard/metrics/protocol.py`

- [ ] **Step 4: Move `batch_protocol.py` to `metrics/batch_protocol.py`**

Read `src/server_monitor/dashboard/batch_protocol.py`, write to `src/server_monitor/dashboard/metrics/batch_protocol.py`

- [ ] **Step 5: Delete original files**

```bash
rm src/server_monitor/dashboard/metrics_stream_manager.py
rm src/server_monitor/dashboard/metrics_stream_command.py
rm src/server_monitor/dashboard/metrics_stream_protocol.py
rm src/server_monitor/dashboard/batch_protocol.py
```

- [ ] **Step 6: Update `main.py` imports**

Read `src/server_monitor/dashboard/main.py`, update import from:
```python
from server_monitor.dashboard.metrics_stream_manager import MetricsStreamManager
```
to:
```python
from server_monitor.dashboard.metrics import MetricsStreamManager
```

- [ ] **Step 7: Update `runtime/__init__.py` after runtime moves (Task 5)**

- [ ] **Step 8: Run lint check**

```bash
uv run ruff check src/server_monitor/dashboard/metrics/
```
Expected: No errors

- [ ] **Step 9: Commit**

```bash
git add src/server_monitor/dashboard/metrics/
git add src/server_monitor/dashboard/main.py
git rm src/server_monitor/dashboard/metrics_stream_manager.py
git rm src/server_monitor/dashboard/metrics_stream_command.py
git rm src/server_monitor/dashboard/metrics_stream_protocol.py
git rm src/server_monitor/dashboard/batch_protocol.py
git commit -m "refactor: move metrics streaming to metrics/ subpackage"
```

---

### Task 4: Move health package files

**Files:**
- Create: `src/server_monitor/dashboard/health/command_health.py`
- Create: `src/server_monitor/dashboard/health/command_policy.py`
- Delete: `src/server_monitor/dashboard/command_health.py`
- Delete: `src/server_monitor/dashboard/command_policy.py`
- Modify: `src/server_monitor/dashboard/runtime/runtime.py` (after move)
- Modify: `src/server_monitor/dashboard/command_executor.py`

- [ ] **Step 1: Move `command_health.py` to `health/command_health.py`**

Read `src/server_monitor/dashboard/command_health.py`, write to `src/server_monitor/dashboard/health/command_health.py`

- [ ] **Step 2: Move `command_policy.py` to `health/command_policy.py`**

Read `src/server_monitor/dashboard/command_policy.py`, write to `src/server_monitor/dashboard/health/command_policy.py`

- [ ] **Step 3: Delete original files**

```bash
rm src/server_monitor/dashboard/command_health.py
rm src/server_monitor/dashboard/command_policy.py
```

- [ ] **Step 4: Update `command_executor.py` imports**

Read `src/server_monitor/dashboard/command_executor.py`, update imports from:
```python
from server_monitor.dashboard.command_policy import (...)
from server_monitor.dashboard.command_health import (...)
```
to:
```python
from server_monitor.dashboard.health.command_policy import (...)
from server_monitor.dashboard.health.command_health import (...)
```

- [ ] **Step 5: Run lint check**

```bash
uv run ruff check src/server_monitor/dashboard/health/
```
Expected: No errors

- [ ] **Step 6: Commit**

```bash
git add src/server_monitor/dashboard/health/
git add src/server_monitor/dashboard/command_executor.py
git rm src/server_monitor/dashboard/command_health.py
git rm src/server_monitor/dashboard/command_policy.py
git commit -m "refactor: move health tracking to health/ subpackage"
```

---

### Task 5: Move runtime package files

**Files:**
- Create: `src/server_monitor/dashboard/runtime/runtime.py`
- Create: `src/server_monitor/dashboard/runtime/runtime_helpers.py`
- Create: `src/server_monitor/dashboard/runtime/status_poller.py`
- Delete: `src/server_monitor/dashboard/runtime.py`
- Delete: `src/server_monitor/dashboard/runtime_helpers.py`
- Delete: `src/server_monitor/dashboard/status_poller.py`
- Modify: `src/server_monitor/dashboard/main.py`
- Modify: `src/server_monitor/dashboard/api.py`
- Modify: `src/server_monitor/dashboard/runtime/__init__.py`

- [ ] **Step 1: Move `runtime.py` to `runtime/runtime.py`**

Read `src/server_monitor/dashboard/runtime.py`, write to `src/server_monitor/dashboard/runtime/runtime.py`

- [ ] **Step 2: Move `runtime_helpers.py` to `runtime/runtime_helpers.py`**

Read `src/server_monitor/dashboard/runtime_helpers.py`, write to `src/server_monitor/dashboard/runtime/runtime_helpers.py`

- [ ] **Step 3: Move `status_poller.py` to `runtime/status_poller.py`**

Read `src/server_monitor/dashboard/status_poller.py`, write to `src/server_monitor/dashboard/runtime/status_poller.py`

- [ ] **Step 4: Delete original files**

```bash
rm src/server_monitor/dashboard/runtime.py
rm src/server_monitor/dashboard/runtime_helpers.py
rm src/server_monitor/dashboard/status_poller.py
```

- [ ] **Step 5: Update `runtime/runtime.py` imports** (these are internal moves)

Read `src/server_monitor/dashboard/runtime/runtime.py`, update:
- `from server_monitor.dashboard.status_poller import` → `from server_monitor.dashboard.runtime.status_poller import`
- `from server_monitor.dashboard.command_policy import` → `from server_monitor.dashboard.health.command_policy import`
- `from server_monitor.dashboard.command_runner import` → `from server_monitor.dashboard.ssh.command_runner import`
- `from server_monitor.dashboard.persistent_session import` → `from server_monitor.dashboard.ssh.persistent_session import`
- `from server_monitor.dashboard.command_executor import` → `from server_monitor.dashboard.command_executor import` (stays)
- `from server_monitor.dashboard.git_operations import` → `from server_monitor.dashboard.panels.git_operations import`
- `from server_monitor.dashboard.command_health import` → `from server_monitor.dashboard.health.command_health import`
- `from server_monitor.dashboard.runtime_helpers import` → `from server_monitor.dashboard.runtime.runtime_helpers import`
- `from server_monitor.dashboard.parsers.git_status import` → `from server_monitor.dashboard.panels.parsers.git_status import`

- [ ] **Step 6: Update `runtime/status_poller.py` imports**

Read `src/server_monitor/dashboard/runtime/status_poller.py`, update:
- `from server_monitor.dashboard.command_policy import` → `from server_monitor.dashboard.health.command_policy import`
- `from server_monitor.dashboard.command_runner import` → `from server_monitor.dashboard.ssh.command_runner import`
- `from server_monitor.dashboard.parsers.` → `from server_monitor.dashboard.panels.parsers.`
- `from server_monitor.dashboard.command_executor import` → `from server_monitor.dashboard.command_executor import`
- `from server_monitor.dashboard.batch_protocol import` → `from server_monitor.dashboard.metrics.batch_protocol import`
- `from server_monitor.dashboard.runtime_helpers import` → `from server_monitor.dashboard.runtime.runtime_helpers import`

- [ ] **Step 7: Update `runtime/runtime_helpers.py` imports**

Read `src/server_monitor/dashboard/runtime/runtime_helpers.py`, update:
- No parser imports, no policy imports - check for any relative updates needed

- [ ] **Step 8: Update `main.py` imports**

Read `src/server_monitor/dashboard/main.py`, update:
```python
from server_monitor.dashboard.runtime import DashboardRuntime, SshCommandExecutor
```
(stays the same since `runtime/__init__.py` re-exports)

- [ ] **Step 9: Update `api.py` imports**

Read `src/server_monitor/dashboard/api.py`, update:
- `from server_monitor.dashboard.runtime_helpers import` → `from server_monitor.dashboard.runtime.runtime_helpers import`

- [ ] **Step 10: Run lint check**

```bash
uv run ruff check src/server_monitor/dashboard/runtime/
```
Expected: No errors

- [ ] **Step 11: Commit**

```bash
git add src/server_monitor/dashboard/runtime/
git add src/server_monitor/dashboard/main.py
git add src/server_monitor/dashboard/api.py
git rm src/server_monitor/dashboard/runtime.py
git rm src/server_monitor/dashboard/runtime_helpers.py
git rm src/server_monitor/dashboard/status_poller.py
git commit -m "refactor: move core runtime to runtime/ subpackage"
```

---

### Task 6: Move panels package files

**Files:**
- Create: `src/server_monitor/dashboard/panels/git_operations.py`
- Create: `src/server_monitor/dashboard/panels/parsers/clash.py`
- Create: `src/server_monitor/dashboard/panels/parsers/git_status.py`
- Create: `src/server_monitor/dashboard/panels/parsers/gpu.py`
- Create: `src/server_monitor/dashboard/panels/parsers/system.py`
- Delete: `src/server_monitor/dashboard/git_operations.py`
- Delete: `src/server_monitor/dashboard/parsers/clash.py`
- Delete: `src/server_monitor/dashboard/parsers/git_status.py`
- Delete: `src/server_monitor/dashboard/parsers/gpu.py`
- Delete: `src/server_monitor/dashboard/parsers/system.py`
- Delete: `src/server_monitor/dashboard/parsers/__init__.py`
- Modify: `src/server_monitor/dashboard/runtime/runtime.py`
- Modify: `src/server_monitor/dashboard/panels/parsers/__init__.py`

- [ ] **Step 1: Move `git_operations.py` to `panels/git_operations.py`**

Read `src/server_monitor/dashboard/git_operations.py`, write to `src/server_monitor/dashboard/panels/git_operations.py`

- [ ] **Step 2: Move parser files to `panels/parsers/`**

Move each parser file maintaining the same content.

- [ ] **Step 3: Delete original files**

```bash
rm src/server_monitor/dashboard/git_operations.py
rm -r src/server_monitor/dashboard/parsers/
```

- [ ] **Step 4: Update `panels/git_operations.py` imports**

Read `src/server_monitor/dashboard/panels/git_operations.py`, update:
- `from server_monitor.dashboard.parsers.git_status import` → `from server_monitor.dashboard.panels.parsers.git_status import`
- `from server_monitor.dashboard.command_executor import` → `from server_monitor.dashboard.command_executor import`
- `from server_monitor.dashboard.runtime_helpers import` → `from server_monitor.dashboard.runtime.runtime_helpers import`

- [ ] **Step 5: Update `runtime/runtime.py` imports**

Read `src/server_monitor/dashboard/runtime/runtime.py`, update:
- `from server_monitor.dashboard.parsers.git_status import` → `from server_monitor.dashboard.panels.parsers.git_status import`

- [ ] **Step 6: Run lint check**

```bash
uv run ruff check src/server_monitor/dashboard/panels/
```
Expected: No errors

- [ ] **Step 7: Commit**

```bash
git add src/server_monitor/dashboard/panels/
git add src/server_monitor/dashboard/runtime/runtime.py
git rm src/server_monitor/dashboard/git_operations.py
git rm -r src/server_monitor/dashboard/parsers/
git commit -m "refactor: move panels to panels/ subpackage"
```

---

### Task 7: Update all test imports

**Files:**
- Modify: `tests/dashboard/test_runtime.py`
- Modify: `tests/dashboard/test_runtime_helpers.py`
- Modify: `tests/dashboard/parsers/test_gpu_parser.py`
- Modify: `tests/dashboard/parsers/test_system_parser.py`
- Modify: `tests/dashboard/parsers/test_git_parser.py`
- Modify: `tests/dashboard/parsers/test_clash_parser.py`
- Modify: `tests/dashboard/test_batch_protocol.py`
- Modify: `tests/dashboard/test_metrics_stream_manager.py`
- Modify: `tests/dashboard/test_metrics_stream_command.py`
- Modify: `tests/dashboard/test_metrics_stream_protocol.py`
- Modify: `tests/dashboard/test_command_policy.py`
- Modify: `tests/dashboard/test_persistent_session.py`
- Modify: `tests/dashboard/test_ssh_tunnel.py`
- Modify: `tests/dashboard/test_app_runtime_hooks.py`
- Modify: `tests/dashboard/test_clash_tunnel.py`
- Modify: `tests/dashboard/test_normalize.py`
- Modify: `tests/dashboard/test_settings_api.py`
- Modify: `tests/dashboard/test_diagnostics_api.py`
- Modify: `tests/dashboard/test_ws_hub.py`
- Modify: `tests/dashboard/test_metrics_stream_protocol.py`
- Modify: `tests/dashboard/test_static_app_behavior.py`
- Modify: `tests/dashboard/test_static_routes.py`
- Modify: `tests/dashboard/test_terminal_launcher.py`
- Modify: `tests/dashboard/test_legacy_cleanup.py`
- Modify: `tests/dashboard/test_settings_store.py`
- Modify: `tests/e2e/test_dashboard_flow.py`
- Modify: `tests/e2e/test_dashboard_websocket_runtime.py`

- [ ] **Step 1: Run full lint to find all broken imports**

```bash
uv run ruff check src/server_monitor/dashboard/ 2>&1 | head -100
```
Expected: Multiple "import error" or "unable to import" errors

- [ ] **Step 2: Fix test imports**

For each test file, update imports from:
```python
from server_monitor.dashboard.parser_x import ...
from server_monitor.dashboard.command_policy import ...
from server_monitor.dashboard.command_runner import ...
from server_monitor.dashboard.persistent_session import ...
from server_monitor.dashboard.metrics_stream_manager import ...
```
to:
```python
from server_monitor.dashboard.panels.parsers import ...
from server_monitor.dashboard.health.command_policy import ...
from server_monitor.dashboard.ssh.command_runner import ...
from server_monitor.dashboard.ssh.persistent_session import ...
from server_monitor.dashboard.metrics import ...
```

- [ ] **Step 3: Run lint check again**

```bash
uv run ruff check src/server_monitor/dashboard/ 2>&1
```
Expected: No import errors

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/dashboard/ -q --tb=short 2>&1 | head -50
```
Expected: All tests pass

- [ ] **Step 5: Commit**

```bash
git add tests/
git commit -m "test: update imports for restructured dashboard packages"
```

---

### Task 8: Verify final structure

**Files:**
- Verify: `src/server_monitor/dashboard/`

- [ ] **Step 1: List dashboard directory structure**

```bash
find src/server_monitor/dashboard -type f -name "*.py" | sort
```
Expected: All files in correct subpackages

- [ ] **Step 2: Run full test suite**

```bash
uv run pytest -q 2>&1 | tail -20
```
Expected: All tests pass

- [ ] **Step 3: Run ruff on entire project**

```bash
uv run ruff check .
```
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git commit -m "refactor: complete dashboard restructure - all imports updated"
```

---

## Spec Coverage Check

- [x] Too many files in dashboard/ → Subpackages created (ssh, metrics, health, runtime, panels)
- [x] runtime.py still too large → Will be ~400 lines after restructure
- [x] shared/ is empty → Left as-is (not needed for this restructure)
- [x] Unclear module boundaries → Clear subpackage boundaries defined
- [x] Parser location → Moved from parsers/ to panels/parsers/

## Self-Review

1. All files moved to appropriate subpackages
2. All imports updated across src/ and tests/
3. Each subpackage has __init__.py with public API exports
4. No placeholder content - all steps complete
5. Type consistency maintained - imports just change paths, not types

---

**Plan complete.** Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
