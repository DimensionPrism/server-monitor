# Git Open In Terminal (Agentless Dashboard) Design

**Date:** 2026-03-11  
**Status:** Approved

## Goal

Add an `Open in Terminal` action to each Git repo card so a single click opens a local terminal and starts an interactive SSH session already inside that repo directory on the remote server.

## Scope

### In Scope (v1)

- New repo-level UI button: `Open in Terminal`.
- Cross-platform local terminal launch support from day one:
  - Windows
  - macOS
  - Linux
- New API route dedicated to this action.
- Server-side validation that target repo is configured in the server's `working_dirs`.
- Safe server-side command construction for interactive SSH in repo.
- Inline per-repo status feedback in existing Git status line.

### Out of Scope (v1)

- Browser-embedded terminal emulation.
- Arbitrary command execution from UI.
- Opening terminals for non-configured paths.
- Additional Git mutation commands beyond existing safe Git ops.

## Architecture

### Backend

- Add API endpoint:
  - `POST /api/servers/{server_id}/git/open-terminal`
  - Request: `{repo_path}`
  - Response: `{ok, launched_with, detail}`
- Extend runtime with:
  - `open_repo_terminal(server_id, repo_path)`
  - Reuse existing server lookup and repo allowlist validation rules.
- Add a local launcher module that:
  - Detects host OS.
  - Chooses available terminal invocation strategy.
  - Runs an SSH command that starts in the selected repo.

### SSH Command Behavior

- Session must open already in repo:
  - `ssh <alias> -t "cd <repo_path> && exec ${SHELL:-bash} -il"`
- Command is constructed only from validated `ssh_alias` and `repo_path`.

### Frontend

- Add `Open in Terminal` button next to existing Git action buttons.
- Bind click handler to call new endpoint.
- Reuse existing per-repo status area for:
  - `opening...`
  - `opened in terminal`
  - failure message

## Cross-Platform Launch Strategy

### Windows

- Preferred: `wt` (Windows Terminal) with command payload.
- Fallback: PowerShell-hosted launch when `wt` is unavailable.

### macOS

- Use `osascript` to instruct Terminal.app to run the SSH command.

### Linux

- Try launchers in order:
  - `x-terminal-emulator`
  - `gnome-terminal`
  - `konsole`
  - `xfce4-terminal`
- Stop at first successful launch; return clear error if none exist.

## Validation and Safety

- Reject unknown server ID (`404`).
- Reject repo path not allowlisted in `working_dirs` (`400`).
- Reject route when runtime or launcher capability is unavailable (`503`).
- No user-provided command fragments accepted.
- Keep quoting/escaping centralized in backend launcher/runtime utilities.

## Error Handling

- Terminal not found on local host:
  - Return `502` with actionable message.
- Spawn failure or immediate process error:
  - Return `502` with concise reason.
- Frontend displays failure inline without disrupting dashboard polling.

## Testing Strategy

### API Tests

- Endpoint dispatches to runtime on success.
- Returns `503` when runtime capability is missing.
- Maps runtime `KeyError`/`ValueError` to HTTP status as expected.

### Runtime Tests

- Unknown server rejected.
- Repo not in allowlist rejected.
- Valid input forwards `ssh_alias` and `repo_path` to launcher.

### Launcher Tests

- OS branch selection via mocked platform detection.
- Safe command construction with special-character paths.
- Fallback order verification when terminal candidates are unavailable.

## Success Criteria

- Clicking `Open in Terminal` opens a new local terminal session.
- Session lands directly in remote repo directory for that card.
- Works on Windows, macOS, and Linux with sensible terminal fallbacks.
- Existing Git actions and dashboard polling remain unchanged.
