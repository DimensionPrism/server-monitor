# Remove Legacy Agent Design

## Goal

Remove the obsolete per-server HTTP agent architecture from the repository so the codebase, tests, configs, and docs describe only the current agentless dashboard.

## Current State

The repo has already pivoted to an agentless dashboard runtime driven by SSH polling, browser settings, and WebSocket updates. Despite that, it still contains the earlier `server_monitor.agent` application, agent-only tests, agent config examples, and legacy planning/spec documents.

Some non-legacy utilities still live under `server_monitor.agent`, especially:

- `command_runner.py`
- parser modules for system, GPU, git, and Clash output

The active dashboard runtime imports those modules directly, so the legacy package cannot simply be deleted without first relocating the reused code.

## Chosen Approach

Move the still-used utilities into dashboard-owned modules, update the agentless runtime to import them from there, then remove the remaining legacy code and documentation entirely.

This keeps the final structure aligned with the actual architecture:

- active runtime code under `server_monitor.dashboard`
- no executable or documented per-server agent path
- no misleading `agent` namespace preserved only for compatibility

## Options Considered

### Option 1: Delete only the runnable agent app and keep `server_monitor.agent` for shared utilities

Pros:

- smallest code movement
- lowest short-term refactor cost

Cons:

- keeps the wrong architecture vocabulary in active code
- makes future maintenance harder because the agentless dashboard still appears to depend on an agent package

### Option 2: Remove `server_monitor.agent` entirely and relocate reused utilities into `server_monitor.dashboard`

Pros:

- matches the actual shipped architecture
- removes legacy concepts from active code
- leaves a simpler mental model for future work

Cons:

- moderate import churn
- requires test and doc updates

### Option 3: Remove `server_monitor.agent` entirely and create a new neutral package for shared runtime utilities

Pros:

- clean naming
- reusable if a second runtime appears later

Cons:

- adds abstraction the current repo does not need
- more structure than the active product justifies

Option 2 was selected.

## Target Code Layout

### Keep

- `src/server_monitor/dashboard/*` for all active runtime, API, settings, and UI behavior

### Add

- `src/server_monitor/dashboard/command_runner.py`
- `src/server_monitor/dashboard/parsers/__init__.py`
- `src/server_monitor/dashboard/parsers/system.py`
- `src/server_monitor/dashboard/parsers/gpu.py`
- `src/server_monitor/dashboard/parsers/git_status.py`
- `src/server_monitor/dashboard/parsers/clash.py`

### Delete

- `src/server_monitor/agent/**`
- `src/server_monitor/shared/**`
- `src/server_monitor/dashboard/poller.py`
- `src/server_monitor/dashboard/config.py`
- `tests/agent/**`
- `tests/shared/**`
- `tests/dashboard/test_poller.py`
- `config/agent.example.toml`
- legacy plan/spec docs that describe the per-server agent architecture

## Migration Sequence

1. Pin current agentless behavior with tests.
2. Move the reused runtime utilities into dashboard-owned modules.
3. Update imports in the active dashboard runtime and tests.
4. Delete the legacy agent package and other dead compatibility files.
5. Delete or rewrite legacy docs and config examples.
6. Run full test and lint verification.

## Testing Strategy

- Add or update tests before code movement when behavior needs to be pinned.
- Preserve current dashboard runtime behavior exactly.
- Remove tests that only validate the deleted agent architecture.
- Keep agentless runtime coverage for:
  - SSH polling
  - parser behavior
  - git operations
  - Clash probing
  - WebSocket broadcasts
  - settings/API flows

## Risks And Mitigations

### Risk: hidden imports still reference `server_monitor.agent`

Mitigation:

- search the repo before and after removal
- update all runtime and test imports in one pass
- run full suite and lint after cleanup

### Risk: deleting shared models breaks active code indirectly

Mitigation:

- verify active imports first
- remove `server_monitor.shared` only after confirming it is agent-only

### Risk: dead docs/config remain and continue to mislead

Mitigation:

- explicitly remove or rewrite all top-level references to per-server agents
- verify remaining `agent` references are either generic English words or intentional historical notes

## Success Criteria

- no active code imports from `server_monitor.agent`
- no `src/server_monitor/agent` package remains
- no agent-only config/examples remain
- no agent-only tests remain
- top-level docs describe only the agentless architecture
- full test suite and lint pass after cleanup
