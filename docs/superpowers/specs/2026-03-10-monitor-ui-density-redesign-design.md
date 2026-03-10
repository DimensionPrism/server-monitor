# Monitor UI Density Redesign (A1) Design

**Date:** 2026-03-10  
**Status:** Approved

## Goal

Redesign the monitor UI to reduce flatness and improve density, using a nested panel structure and multi-server desktop layout while preserving existing data and controls.

## Scope

### In Scope

- Desktop monitor layout: two server cards side-by-side when space allows (A1).
- Nested section structure within each server card using collapsible groups.
- GPU panel rendered as auto-fit tile grid that supports any GPU count.
- Git and Clash sections collapsed by default to reduce visual noise.
- Preserve existing Git safe operation controls and status messages.

### Out of Scope

- Backend API schema changes.
- Server tab navigation mode.
- Additional operations or data sources.

## Layout Model

### Server Board

- `monitor-grid` becomes a board optimized for 2 visible server cards on desktop.
- Responsive fallback to single-column stack on narrower screens.

### Server Card Nested Sections

Per server card:

1. `System` section (expanded by default)
2. `GPU` section (expanded by default)
3. `Git` section (collapsed by default)
4. `Clash` section (collapsed by default)

Nested sections use semantic `<details><summary>` wrappers for accessibility and keyboard support.

## GPU Grid Behavior

- GPU tiles use CSS auto-fit layout (`repeat(auto-fit, minmax(...))`).
- Tile count and wrapping are fully data-driven (no fixed 2x4 assumption).
- Works for any server GPU count (2, 8, 16, etc.).

## Visual Direction

- Keep current terminal-inspired palette but increase hierarchy via:
  - section headers with stronger contrast
  - nested group depth cues
  - tighter spacing and compact tile metrics
- Avoid flat monolithic blocks by introducing explicit card-within-card rhythm.

## Interaction Behavior

- Preserve existing panel toggles from server settings.
- Preserve existing Git action buttons and inline status messages.
- Collapsed sections remain user-controlled in current session.

## Testing Strategy

- Static route tests assert nested UI markup markers are present in `app.js`.
- Existing monitor runtime/API tests remain unchanged (no schema changes).
- Full lint/test suite run to prevent regressions.

## Success Criteria

- Desktop displays both servers side-by-side when viewport permits.
- Each server card shows nested sections with default open/closed behavior.
- GPU panel automatically adapts to any GPU count without hardcoded dimensions.
- Git controls still function and remain visible when Git section is expanded.