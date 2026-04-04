# Simplify runtime.py - Split by Domain

## Status

Approved

## Problem

`runtime.py` is 2185 lines with 37 top-level definitions handling multiple unrelated responsibilities: SSH execution, metrics streaming, status polling, git operations, clash management, command health tracking, and serialization. This violates single responsibility and makes the code hard to navigate and test.

## Solution

Split `runtime.py` into focused modules by polling domain, with a thin orchestrator remaining in `runtime.py`.

## New File Structure

```
src/server_monitor/dashboard/
├── runtime.py              # Thin orchestrator (~400 lines)
├── status_poller.py        # Status polling logic (~350 lines)
├── git_operations.py       # Git polling and operations (~200 lines)
├── command_health.py       # Health tracking and summaries (~250 lines)
├── runtime_helpers.py      # Pure helper functions (~500 lines)
```

## Module Responsibilities

### runtime.py
- `DashboardRuntime` - Coordinates polling, caching, broadcasting across domains
- `SshCommandExecutor` - SSH execution (already independent, unchanged)
- Dataclasses: `_MetricsStreamStatus`, `_PolicyExecutionOutcome`, `_SkippedCommandResult`
- Key methods: `start()`, `_poll_server()`, `_broadcast_server_state()`

### status_poller.py
Owns all status polling logic:
- `_poll_metrics()`, `_poll_metrics_batch()`
- `_poll_status_panels()`
- `_is_status_poll_inflight()`, `_consume_finished_status_poll_task()`, `_consume_status_poll_task_result()`
- `_start_status_poll_if_needed()`

### git_operations.py
Owns git polling and operations:
- `_poll_git_repos()`, `_poll_single_git_repo()`
- `_run_git_operation_command()`
- `_replace_cached_repo()`, `_empty_repo_status()`

### command_health.py
Owns command health tracking:
- `_failure_tracker_for()`, `_append_command_health()`
- `_summarize_server_command_health()`, `_latest_command_health_record()`
- `_command_health_*` helpers: `_state_from_record()`, `_label()`, `_severity()`, `_summary_from_record()`, `_detail()`
- `_worst_command_health_state()`

### runtime_helpers.py
Pure standalone functions extracted from runtime.py:
- **Command builders:** `_system_command()`, `_gpu_command()`, `_git_status_command()`, `_git_operation_command()`, `_clash_command()`, `_batched_clash_secret_command()`, `_batched_clash_probe_command()`
- **Serializers:** `_serialize_runtime_settings()`, `_serialize_metrics_stream_status()`
- **Utilities:** `_needs_status_poll()`, `_metrics_sleep_seconds()`, `_is_ssh_unreachable()`, `_shell_quote()`, `_group_batch_sections()`, `_find_server()`, `_should_retry()`, `_build_freshness_entry()`, `_age_seconds_from_iso()`, `_metrics_stream_transport_latency_ms()`, `_metrics_stream_latency_upper_bound_ms()`, `_extract_clash_secret()`, `_parse_required_clash_secret()`, `_is_valid_branch_name()`

## Data Flow

```
DashboardRuntime.start()
  └── _poll_server()
        ├── status_poller._poll_status_panels()
        │     ├── _poll_metrics() / _poll_metrics_batch()
        │     └── outcome → command_health._append_command_health()
        ├── git_operations._poll_git_repos()
        │     └── outcome → command_health._append_command_health()
        └── _broadcast_server_state()
              └── uses runtime_helpers._serialize_runtime_settings()
```

## Import Structure

- `runtime.py` imports from: `status_poller`, `git_operations`, `command_health`, `runtime_helpers`, plus existing dashboard modules
- `status_poller.py`, `git_operations.py`, `command_health.py`, `runtime_helpers.py` - no cross-imports; only called by runtime

## Constraints

- No behavior changes - only refactoring
- All existing tests must pass
- `DashboardRuntime` public API remains unchanged (`__init__` signature, `start()`, public methods used by `api.py`)
- Internal method signatures may change but must not break internal callers within the split modules
