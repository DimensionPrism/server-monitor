# Safe Git Ops (Agentless Dashboard) Design

**Date:** 2026-03-10  
**Status:** Approved

## Goal

Add guarded git controls to the local dashboard so each configured repo can run low-risk operations over SSH: refresh status, fetch, pull (fast-forward only), and checkout branch.

## Scope

### In Scope (v1)

- API endpoint for safe git operations.
- Strict operation allowlist: `refresh`, `fetch`, `pull`, `checkout`.
- Validation that target server exists and repo path is in configured `working_dirs`.
- Branch input validation for checkout.
- UI controls in Git panel to trigger operations and show per-repo result feedback.
- Immediate repo status refresh returned from operation API.

### Out of Scope (v1)

- Stage/commit/push/reset/clean/rebase/cherry-pick.
- Multi-step operation queues and history persistence.
- Repo creation, cloning, or remote filesystem editing.

## Architecture

### Backend

- Extend dashboard runtime with `run_git_operation(...)` helper:
  - Builds safe command from allowlist.
  - Executes command via existing SSH executor.
  - Re-runs `git status --porcelain --branch` and parses status.
  - Returns structured result with operation metadata and refreshed repo state.
- Add API route:
  - `POST /api/servers/{server_id}/git/ops`
  - Request: `{repo_path, operation, branch?}`
  - Response: `{ok, operation, command, exit_code, stderr, repo}`

### Frontend

- Git panel per repo row includes:
  - `Refresh`, `Fetch`, `Pull` buttons.
  - Branch text input + `Checkout` button.
- Show operation status line (`running/success/fail`) next to each repo.
- Update in-memory repo state from API response, without waiting for poll interval.

## Validation & Safety

- Reject unknown server IDs (`404`).
- Reject repo paths not listed in configured server `working_dirs` (`400`).
- Reject unsupported operations (`400`).
- Reject invalid checkout branch names (`400`) using conservative pattern.
- Keep shell quoting for repo and branch arguments.
- Pull command uses `--ff-only` to avoid implicit merge commits.

## Error Handling

- SSH/command failures return `ok=false` with stderr and exit code.
- API still attempts post-op status refresh when possible.
- Frontend shows inline failure but keeps monitor active.

## Testing Strategy

- API tests for validation and operation dispatch.
- Runtime tests for command mapping and status refresh behavior.
- Frontend smoke checks for rendering operation controls and status updates.

## Success Criteria

- User can trigger safe git ops from dashboard UI for configured repos.
- Unsafe repo paths/operations are blocked server-side.
- Repo status updates immediately after operation call.
- Existing polling/dashboard behavior remains stable.