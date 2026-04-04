# Extract CommandExecutor from runtime.py

## Status

Approved

## Problem

`runtime.py` is still ~1150 lines after the first round of extraction. The `DashboardRuntime` class holds large method bodies (`_execute_with_policy` ~170 lines, `_record_batch_section_outcome` ~100 lines) that mix policy execution logic with cache/state mutation.

## Solution

Extract a `CommandExecutor` class from `DashboardRuntime` to own all command execution with retry/policy logic.

## New File

```
src/server_monitor/dashboard/command_executor.py
```

## CommandExecutor Class

### Responsibility
Owns all command execution with retry logic, policy enforcement, and batch outcome recording.

### Methods

| Method | Source line | Purpose |
|--------|-------------|---------|
| `execute_with_policy` | runtime.py:650 | Retry loop with CommandPolicy, calls runner |
| `record_batch_failure` | runtime.py:824 | Records batch command failure |
| `record_batch_section_outcome` | runtime.py:879 | Parses batch section and records outcome |

### Data Classes (move from runtime.py)
- `_PolicyExecutionOutcome` (runtime.py:49)
- `_SkippedCommandResult` (runtime.py:60)

## What Stays in runtime.py

- `SshCommandExecutor` class (unchanged)
- `DashboardRuntime` class (orchestrator, slimmed)
- `_MetricsStreamStatus` dataclass
- Execution helpers: `_run_executor`, `_run_batch_executor`, `_run_git_operation_command`
- Public API methods: `run_git_operation`, `open_repo_terminal`, `get_recent_command_health`, `build_diagnostics_bundle`
- Metrics stream handlers
- Health tracker stubs (delegates to `_health`)

## Expected Result

- `runtime.py`: ~1150 → ~700 lines (40% reduction)
- `command_executor.py`: ~350 lines

## Constraints

- No behavior changes
- All tests pass
- `DashboardRuntime.__init__` signature unchanged
- Internal method signatures may change
