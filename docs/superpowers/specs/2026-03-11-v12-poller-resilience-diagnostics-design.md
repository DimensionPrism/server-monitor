# v1.2 Poller Resilience and Diagnostics Design

## Summary

The next roadmap step should be `v1.2 phase 1`: harden the agentless poller before adding more UI surface area.

The codebase already has the right high-level shape for this:

- `DashboardRuntime` decides what to poll and when
- `CommandRunner` executes local `ssh` processes with timeout control
- runtime caches already preserve last-known-good data on transient failures

The gap is that resiliency policy is still implicit and scattered across constants and call sites. `v1.2 phase 1` should add a small command policy layer plus an in-memory health journal so the runtime can:

- retry transient failures in a bounded way
- avoid retry storms on repeatedly failing commands
- preserve last-known-good snapshots with explicit failure reasons
- export recent failure and latency evidence as a shareable diagnostics bundle

## Scope

### In Scope

- Agentless dashboard backend only
- Bounded retry/backoff policies per command kind
- Command failure classification for polling and git operations
- Short cooldowns after repeated failures to avoid hammering bad targets
- In-memory recent command health journal
- Exportable diagnostics bundle API with redaction-safe contents
- Tests for policy behavior, runtime integration, diagnostics export, and redaction

### Out of Scope

- Historical storage or charts
- New monitor dashboard UI for command telemetry
- Notification delivery
- Multi-user auth or role controls
- Remote backend abstraction beyond SSH
- Persisting diagnostics to disk by default

## Requirements

1. The runtime must stay agentless and preserve the existing dashboard payload shape for monitor data.
2. Retry behavior must be policy-driven per command kind rather than hard-coded ad hoc at each call site.
3. Only transient failure classes are retryable:
   - timeout
   - SSH transport/unreachable failures
   - selected non-zero exit failures where the command kind explicitly allows retry
4. Parse failures and invalid user-triggered git operations must fail fast without retry.
5. Retry behavior must remain bounded:
   - small retry counts
   - small backoffs
   - cooldown after repeated failures
6. Existing cache fallback behavior must remain intact:
   - last-known-good system/GPU/git/clash data is preserved on transient poll failures
7. The system must keep enough recent execution evidence to explain:
   - what failed
   - how many attempts were made
   - how long it took
   - whether cached data was used
8. Diagnostics export must be safe to share:
   - include current settings and recent command outcomes
   - redact secrets and secret-bearing command text
   - keep probe URLs and declared repo paths visible

## Proposed Module Boundaries

### `src/server_monitor/dashboard/command_policy.py`

New focused module for resilience policy and health recording primitives.

Responsibilities:

- define `CommandKind`
- define `CommandPolicy`
- classify failures
- compute retry delay and cooldown state
- define the journal record shape for recent command outcomes

### `src/server_monitor/dashboard/runtime.py`

Remain the orchestration layer.

Responsibilities:

- choose which commands to run for each poll cycle
- route command execution through the policy wrapper
- update caches/freshness exactly as today
- append redaction-safe health records to the journal

### `src/server_monitor/dashboard/api.py`

Expose diagnostics export without moving poll logic into the API layer.

Responsibilities:

- add diagnostics route
- return a JSON diagnostics bundle built from runtime state

## Command Policy Design

### Command Kinds

The runtime should name each remote command by intent rather than by raw command string:

- `system`
- `gpu`
- `git_status`
- `clash_secret`
- `clash_probe`
- `git_operation`

This keeps policy decisions stable even if the exact shell command changes later.

### Policy Shape

Each command kind gets a policy with:

- `timeout_seconds`
- `max_attempts`
- `base_backoff_seconds`
- `retry_on_timeout`
- `retry_on_ssh_error`
- `retry_on_nonzero_exit`
- `cooldown_after_failures`
- `cooldown_seconds`

Suggested starting defaults:

- `system`: 2 attempts, short timeout, short backoff
- `gpu`: 2 attempts, short timeout, short backoff
- `git_status`: 2 attempts, moderate timeout, short backoff
- `clash_secret`: 2 attempts, short timeout, short backoff
- `clash_probe`: 2 attempts, short timeout, short backoff
- `git_operation`: 1 attempt for validation failures, longer timeout for remote execution failures

The first implementation should keep the policy table local and static in Python, not user-configurable.

### Failure Classes

Execution results should be normalized into stable classes:

- `ok`
- `timeout`
- `ssh_unreachable`
- `nonzero_exit`
- `parse_error`
- `invalid_request`
- `unexpected`
- `cooldown_skip`

These classes are for resilience decisions and diagnostics summaries. They do not replace user-facing monitor messages.

## Runtime Execution Flow

### Policy Wrapper

Replace direct runtime calls to the executor with one wrapper:

`execute_with_policy(server_id, command_kind, target_label, remote_command, policy)`

The wrapper should:

1. Run the first attempt.
2. Classify the outcome.
3. Retry only when the policy allows it.
4. Sleep using bounded backoff between attempts.
5. Record one health sample for the whole execution, including:
   - attempts used
   - total duration
   - final failure class
   - whether cached data remained in use
6. Update per-target cooldown state when failure streak thresholds are crossed.

### Cooldown Behavior

Cooldown is intentionally short and local. It is not a circuit breaker subsystem.

When a command target crosses its configured failure streak:

- the runtime does not immediately hammer it again on the next cycle
- the next scheduled poll can emit a `cooldown_skip` health record
- cached panel data remains available if present

Examples:

- repeated `clash_secret` timeouts should not block every status cycle
- repeatedly failing `git_status` for one repo should not degrade unrelated repos

### Cache and Freshness Semantics

Current cache behavior should stay intact. `v1.2` adds execution evidence, not a new freshness model.

The runtime should continue to:

- update caches on successful polls
- keep cached system/GPU/git/clash data on transient failures
- mark panel freshness as cached when the last poll failed

What changes is that the runtime will now know why a panel fell back to cache:

- poll error after retries exhausted
- cooldown skip after repeated failures
- no prior data

## Health Journal Design

### Retention

Keep a small in-memory ring buffer per server and target.

Suggested retention:

- last 20 command outcomes per `(server_id, command_kind, target_label)`

This is enough for current debugging needs without introducing storage or retention management complexity.

### Recorded Fields

Store only redaction-safe fields:

- `recorded_at`
- `server_id`
- `command_kind`
- `target_label`
- `ok`
- `failure_class`
- `attempt_count`
- `duration_ms`
- `attempt_durations_ms`
- `exit_code`
- `cooldown_applied`
- `cache_used`
- `message`

Do not store:

- raw Clash secrets
- auth headers
- raw remote commands containing secrets

If a failure message can contain a secret, redact it before journaling.

## Diagnostics Bundle Design

### Transport

Add a backend endpoint that returns a JSON diagnostics bundle:

- `GET /api/diagnostics`

This is sufficient for export and sharing. A UI download button can be added later without redesigning the backend payload.

### Bundle Contents

The bundle should include:

- `generated_at`
- current dashboard settings with redaction applied
- per-server recent command summaries
- recent failures and retry evidence per target
- latency summary per command kind and target

Suggested top-level shape:

```json
{
  "generated_at": "2026-03-11T10:00:00+00:00",
  "settings": {
    "metrics_interval_seconds": 3.0,
    "status_interval_seconds": 12.0,
    "servers": []
  },
  "servers": [
    {
      "server_id": "server-a",
      "commands": [
        {
          "command_kind": "system",
          "target_label": "server",
          "recent_outcomes": [],
          "summary": {
            "success_count": 0,
            "failure_count": 0,
            "avg_duration_ms": 0,
            "last_failure_class": "ok"
          }
        }
      ]
    }
  ]
}
```

### Redaction Rules

Redact:

- Clash secrets
- bearer tokens
- secret-bearing fragments in stderr/stdout excerpts

Keep:

- SSH alias
- configured probe URLs
- configured repo paths
- stable failure classes
- durations, retry counts, exit codes

The first version should prefer omission over risky partial disclosure. If a detail is not clearly safe, do not include it.

## Error Handling

### Poller Resilience

- Timeouts and SSH transport errors can retry according to policy.
- Parse errors fail fast and keep cached data if available.
- When retries exhaust, the final health sample must reflect the last failure class and attempt count.
- Cooldown skips must not look like successes.

### Diagnostics Export

- Diagnostics route should succeed even when no runtime data exists yet.
- Empty journal output is valid and should produce an empty bundle rather than a server error.
- If the runtime is unavailable, the API should return `503`.

## Testing Plan

### New Policy Tests

Add focused tests for:

- retryable vs non-retryable failure classes
- backoff calculation
- cooldown threshold behavior
- redaction of secret-bearing text

### Runtime Tests

Add or extend tests for:

- transient timeout succeeds on retry for system/GPU polling
- parse failure does not retry
- repeated failure leads to cooldown on a later cycle
- cached data survives retries and cooldown
- git repo failures remain isolated per repo

### Diagnostics API Tests

Add tests for:

- diagnostics endpoint returns empty-but-valid bundle
- settings are included
- recent command health records are included
- secret values are redacted
- route returns `503` when runtime support is absent

## Acceptance Criteria

1. Poll commands run through a named policy layer rather than direct ad hoc executor calls.
2. Transient failures are retried in a bounded way and repeated failures trigger short cooldowns.
3. Existing cache fallback behavior remains intact for system, GPU, git, and Clash.
4. Recent command health evidence is retained in memory without storing secrets.
5. `GET /api/diagnostics` returns a shareable redaction-safe bundle of current settings plus recent command outcomes.
6. Dashboard backend tests and lint remain green after the change.
