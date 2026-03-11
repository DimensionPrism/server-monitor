# Dashboard UI Add Card Collapse Adjustment Design

**Date:** 2026-03-11  
**Status:** Approved

## Goal

Adjust the premium settings workspace so the `Add Server` card is only fully open for first-run setup, then collapses into a compact reopen flow once at least one server exists.

## Decision Summary

- If there are `0` saved servers, the add card is expanded by default.
- After a successful add, the add card collapses immediately.
- If there is at least `1` saved server, the settings view loads with the add card collapsed by default.
- A dedicated `Add Server` button reopens the card.
- Collapsing the add card resets the form instead of preserving an unsaved draft.

## Interaction Model

### First Run

- The settings view should prioritize server creation when the system is empty.
- The add form remains fully visible until the first server is successfully created.

### Post-Setup

- Once a server has been created, the add form should stop dominating the top of the settings workspace.
- The collapsed state should become the default for any later visit where at least one server already exists.
- Reopening should be explicit through a dedicated `Add Server` button positioned above the workspace.

### Collapse Behavior

- Collapsing the card must reset all temporary add-form input state.
- Reopening the card must restore the default blank form:
  - empty `server_id`
  - empty `ssh_alias`
  - empty `working_dirs`
  - default Clash probe URLs
  - all built-in panels checked

## Visual and Layout Implications

- The reopen button should feel consistent with the premium settings workspace, not like a utility link.
- The collapsed add-card state should reduce vertical weight at the top of the settings view without introducing a second dense toolbar.
- The rest of the split settings layout remains unchanged:
  - left overview rail
  - right focused editor canvas
  - sticky editor footer

## Implementation Boundary

Primary files:

- `src/server_monitor/dashboard/static/index.html`
- `src/server_monitor/dashboard/static/app.js`
- `src/server_monitor/dashboard/static/styles.css`
- `tests/dashboard/test_static_routes.py`
- `tests/dashboard/test_static_app_behavior.py`

No backend or settings-schema changes are required.

## Testing Strategy

- Extend static-route tests for the add-card toggle hook and collapsed-state hooks.
- Extend Node-backed app behavior tests for:
  - default-open when server list is empty
  - default-collapsed when server list is non-empty
  - immediate collapse after successful add
  - add-form reset on collapse
- Run:
  - `uv run pytest -q`
  - `uv run ruff check .`

## Success Criteria

- First-run setup still feels obvious when no servers exist.
- After the first successful add, the add form collapses immediately.
- Later visits with existing servers start with the add card collapsed.
- The `Add Server` button cleanly reopens the form.
- Collapsing the add card clears any unsaved add-form draft.
