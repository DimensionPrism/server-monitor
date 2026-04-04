# Codebase Structure Optimization Design

**Date:** 2026-04-04
**Status:** Draft

## Goal

Restructure `src/server_monitor/dashboard/` to improve maintainability by grouping related files into focused subpackages, reducing flat-file clutter, and creating clearer module boundaries.

## Problems Identified

1. **Too many files in `dashboard/`**: 25 files at the top level makes navigation difficult
2. **`runtime.py` at 869 lines**: Despite prior extractions, still handles too many concerns (polling, broadcasting, health tracking, git operations, metrics streaming coordination)
3. **`shared/` is empty**: No actual shared utilities despite the package existing
4. **Unclear boundaries**: Files like `status_poller.py`, `git_operations.py`, `command_executor.py` are all top-level with no grouping

## Proposed Structure

```
src/server_monitor/
├── __init__.py
├── shared/
│   └── __init__.py          # Empty marker for now
├── agent/
│   └── [existing agent code]
└── dashboard/
    ├── __init__.py
    ├── api.py               # FastAPI routes (top-level per FastAPI convention)
    ├── cli.py               # CLI entrypoint
    ├── main.py              # App factory
    ├── settings.py          # Settings models and store
    ├── ws_hub.py            # WebSocket hub
    ├── normalize.py         # Payload normalization
    ├── clash_tunnel.py     # Clash tunnel manager
    ├── terminal_launcher.py # Terminal launcher
    ├── command_executor.py  # Command executor (already extracted)
    ├── ssh/                 # SSH transport layer
    │   ├── __init__.py
    │   ├── command_runner.py
    │   ├── persistent_session.py
    │   └── ssh_tunnel.py
    ├── metrics/             # Metrics streaming subsystem
    │   ├── __init__.py
    │   ├── manager.py           # MetricsStreamManager
    │   ├── command.py           # MetricsStreamCommand
    │   ├── protocol.py          # MetricsStreamProtocol
    │   └── batch_protocol.py    # BatchProtocol
    ├── health/              # Command health tracking subsystem
    │   ├── __init__.py
    │   ├── command_health.py    # CommandHealthTracker
    │   └── command_policy.py     # CommandPolicy, FailureTracker
    ├── runtime/             # Core polling runtime
    │   ├── __init__.py
    │   ├── runtime.py           # DashboardRuntime, SshCommandExecutor
    │   ├── runtime_helpers.py   # Runtime helper functions
    │   └── status_poller.py     # StatusPoller
    └── panels/              # Panel data collection
        ├── __init__.py
        ├── git_operations.py    # GitOperations
        └── parsers/
            ├── __init__.py
            ├── clash.py
            ├── git_status.py
            ├── gpu.py
            └── system.py
```

## New Subpackage Definitions

### `ssh/` — SSH Transport Layer
Handles SSH connection and command execution.
- `CommandRunner`: Executes remote commands via SSH
- `PersistentBatchTransport`: Persistent SSH session for batch commands
- `ssh_tunnel.py`: SSH tunnel functionality

**Public API:**
```python
from server_monitor.dashboard.ssh import CommandRunner, PersistentBatchTransport
```

### `metrics/` — Metrics Streaming
Handles streaming metrics from servers.
- `MetricsStreamManager`: Manages metrics stream lifecycle
- `MetricsStreamCommand`: Command model for streams
- `MetricsStreamProtocol`: Protocol for parsing stream data
- `BatchProtocol`: Batch command protocol

**Public API:**
```python
from server_monitor.dashboard.metrics import MetricsStreamManager
```

### `health/` — Command Health Tracking
Tracks command execution health and failures.
- `CommandHealthTracker`: Tracks health records per server/command
- `CommandPolicy`: Defines policies for command execution (cooldown, retry)
- `FailureTracker`: Tracks consecutive failures

**Public API:**
```python
from server_monitor.dashboard.health import CommandHealthTracker, CommandPolicy
```

### `runtime/` — Core Polling Runtime
Coordinates polling, broadcasting, and server state management.
- `DashboardRuntime`: Main runtime orchestrator (reduce from ~869 to ~400 lines)
- `StatusPoller`: Handles status panel polling
- `runtime_helpers.py`: Helper functions for runtime

**Public API:**
```python
from server_monitor.dashboard.runtime import DashboardRuntime, StatusPoller
```

### `panels/` — Panel Data Collection
Collects data for git and clash panels.
- `GitOperations`: Git repo status polling and operations
- `parsers/`: Output parsers for SSH command results

**Public API:**
```python
from server_monitor.dashboard.panels.git_operations import GitOperations
from server_monitor.dashboard.panels.parsers import parse_gpu, parse_system
```

## Migration Steps

### Phase 1: Create Subpackage Skeleton
1. Create `ssh/`, `metrics/`, `health/`, `runtime/`, `panels/`, `panels/parsers/` directories
2. Add `__init__.py` to each
3. Move files one subpackage at a time

### Phase 2: Move SSH Package
- Move `command_runner.py` → `ssh/command_runner.py`
- Move `persistent_session.py` → `ssh/persistent_session.py`
- Move `ssh_tunnel.py` → `ssh/ssh_tunnel.py`
- Update `__init__.py` to export public types

### Phase 3: Move Metrics Package
- Move `metrics_stream_manager.py` → `metrics/manager.py`
- Move `metrics_stream_command.py` → `metrics/command.py`
- Move `metrics_stream_protocol.py` → `metrics/protocol.py`
- Move `batch_protocol.py` → `metrics/batch_protocol.py`

### Phase 4: Move Health Package
- Move `command_health.py` → `health/command_health.py`
- Move `command_policy.py` → `health/command_policy.py`

### Phase 5: Move Runtime Package
- Move `runtime.py` → `runtime/runtime.py`
- Move `runtime_helpers.py` → `runtime/runtime_helpers.py`
- Move `status_poller.py` → `runtime/status_poller.py`

### Phase 6: Move Panels Package
- Move `git_operations.py` → `panels/git_operations.py`
- Move `parsers/clash.py` → `panels/parsers/clash.py`
- Move `parsers/git_status.py` → `panels/parsers/git_status.py`
- Move `parsers/gpu.py` → `panels/parsers/gpu.py`
- Move `parsers/system.py` → `panels/parsers/system.py`

### Phase 7: Update Import Paths
Update all import statements across the codebase:
- `src/server_monitor/dashboard/**/*.py`
- `tests/**/*.py`
- `docs/**/*.py` (if any code references)

### Phase 8: Verify
- Run `uv run ruff check .` to verify no import errors
- Run `uv run pytest -q` to verify all tests pass

## Backward Compatibility

All public APIs will be re-exported from `__init__.py` files where appropriate to minimize breaking changes for external consumers.

## Files Remaining at Top Level

These files stay at the top level of `dashboard/` because they have special placement requirements:
- `api.py` — FastAPI convention to be discoverable
- `cli.py` — Entry point
- `main.py` — App factory
- `settings.py` — Settings models
- `ws_hub.py` — Used by api.py
- `normalize.py` — Utility used widely
- `clash_tunnel.py` — Used by api.py
- `terminal_launcher.py` — Utility
- `command_executor.py` — Already extracted, used by runtime

## Estimated Impact

| Metric | Before | After |
|--------|--------|-------|
| Files at dashboard/ root | 25 | 9 |
| Max file lines (runtime.py) | ~869 | ~400 |
| Subpackages | 0 | 5 |
| Parser location | `parsers/` | `panels/parsers/` |

## Test Updates

Tests in `tests/dashboard/` will need updated import paths:
- `tests/dashboard/test_runtime.py` → imports from `server_monitor.dashboard.runtime`
- `tests/dashboard/parsers/` → imports from `server_monitor.dashboard.panels.parsers`
- etc.

Tests should remain in `tests/dashboard/` maintaining their current organization.
