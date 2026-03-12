# Dashboard Git Op Transport Fix Design

**Date:** 2026-03-12
**Status:** Approved

## Goal

Fix dashboard git operations that fail in the long-running app process while preserving the existing API and safety model.

## Root Cause

The live dashboard keeps background git status polling healthy through the persistent SSH shell transport, but `run_git_operation()` still opens a separate one-shot SSH subprocess for `fetch`, `pull`, and `checkout`. In the long-running process, that one-shot path can wedge and hit the 20 second timeout even when the same remote git command succeeds directly and on a fresh app instance.

## Design

- Reuse the existing persistent batch transport for git operations.
- Keep the current one-shot SSH executor as a fallback if the persistent transport fails.
- Preserve the current API response shape and allowlist validation.
- Add session-level locking inside the persistent transport so status polling and interactive git operations cannot interleave requests on the same alias.

## Scope

### In Scope

- Runtime git operation execution path
- Persistent transport serialization for same-alias requests
- Regression tests for `fetch`, `pull`, `checkout`, and fallback behavior

### Out of Scope

- Changing the git operation allowlist
- Refactoring the polling architecture
- Investigating the deeper cause of the one-shot SSH path instability beyond preserving fallback

## Verification

- Runtime tests show git ops prefer persistent transport when available.
- Runtime tests show git ops fall back to one-shot SSH if persistent transport fails.
- Persistent-session tests show concurrent same-alias requests are serialized.
- Fresh app instance reproductions for `fetch`, `pull`, and `checkout` succeed through the updated runtime path.
