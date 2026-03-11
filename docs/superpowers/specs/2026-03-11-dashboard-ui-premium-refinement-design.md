# Dashboard UI Premium Refinement Design

**Date:** 2026-03-11  
**Status:** Approved

## Goal

Refine the dashboard from the first visual optimization pass into a more premium-feeling operator surface while preserving the current summary-first information model and safer settings workflow.

## User Priorities

- Premium visual feel is the top priority for this pass.
- Settings editing polish is the second priority.
- The existing summary-first monitor structure should remain intact.
- The existing settings draft-preservation behavior must remain intact.
- Settings should keep the add-first flow with the add form always visible.
- Summary metrics should always be color-coded by utilization.
- GPU heat cues should stay local to GPU contexts and must not escalate the whole server card.
- Motion can be more present than the previous pass as long as it stays purposeful.

## Scope

### In Scope

- Premium surface, typography, shadow, and motion refinements across the static frontend.
- Always-on semantic coloring for summary metrics and meter bars.
- Heat-aware GPU styling in GPU tiles and GPU-related meter contexts.
- Settings workspace refinement into an always-open add card, left-side overview rail, and right-side focused editor canvas.
- Grouped settings editor cards and a sticky footer with stronger save/delete hierarchy.

### Out of Scope

- Backend API or settings schema changes.
- New monitoring panels, server actions, or data sources.
- Whole-card escalation for GPU heat.
- Replacing the existing summary-first monitor model.
- Browser automation or framework migration.

## Settings Workspace Layout

The Settings tab should use a three-zone desktop workspace:

1. an always-open `Add Server` card at the top
2. a compact overview rail of configured servers on the left
3. a wide focused editor canvas on the right

The add card must stay open even when servers already exist. This preserves the add-first workflow and keeps the tab useful for both first-time setup and ongoing operations.

The overview rail remains selection-first, not edit-in-place. Each row should summarize:

- server id
- SSH alias
- working-directory count
- enabled panel badges
- probe-status hint

The focused editor is the only full editing surface. It should be structured as grouped cards rather than a single uninterrupted form:

- `Identity`
- `Monitoring Targets`
- `Panels`
- `Clash Probes`

The editor should end with a sticky action footer that remains visible while the editor pane scrolls. `Save` is the dominant action. `Delete` stays visually quieter and clearly separated from save.

## Monitor Visual Direction

The monitor should follow a premium instrument-panel direction rather than a louder signal-board direction.

### Core Treatment

- Keep the existing summary-first server cards.
- Increase perceived quality through layered surfaces, stronger type contrast, richer shadows, refined meter styling, and cleaner motion.
- Keep the current GPU summary semantics:
  - primary: `active/total`
  - secondary: `peak %`

### Semantic Color

- Summary metrics and meter bars should always be color-coded by utilization.
- Semantic color should be readable at a glance without making the board look like an alert wall.

### GPU Heat Rules

Heat-aware color belongs only in GPU-specific contexts:

- GPU tiles
- GPU meter bars
- GPU summary/meter treatment

Heat must not recolor or glow the entire server card.

## Settings Interaction and Visual Hierarchy

The settings editor should feel like a premium control surface rather than a utility form.

### Behavior

- Preserve the current per-server draft behavior when switching selected rows.
- Animate row selection and focused-editor transitions so the rail and editor feel connected.
- Use sticky-footer states to reflect editor status:
  - neutral when clean
  - stronger emphasis when dirty
  - brief success confirmation after save

### Card Structure

- `Identity` stays compact and topmost.
- `Monitoring Targets` gets the largest card because the multiline paths input needs the most room.
- `Panels` and `Clash Probes` can share a row on desktop and stack on mobile.
- Each card should include a small heading and restrained helper text.

### Action Hierarchy

- `Save` becomes a premium primary action with deeper gradient, lift, and press feedback.
- `Delete` stays ghost/secondary until hover or focus.
- Status messaging should live near the sticky footer instead of floating in the body of the form.

### Field Treatment

- Inputs and textareas should use larger padding and stronger active/focus states.
- Focus should use accent color plus a subtle internal glow.
- Card-level spacing should make the editor read as a sequence of deliberate sections.

## Motion and Interaction

Motion can be richer than in the previous pass, but it must stay functional.

- Animate detail-section expansion and collapse.
- Add hover lift and press feedback on cards and buttons.
- Smoothly animate meter or bar state changes.
- Refine focus transitions for interactive controls.

Avoid motion that changes layout meaningfully or creates constant visual distraction.

## Visual System

- Keep the dark operator palette, but deepen the surfaces with more layered depth.
- Increase contrast between primary metric typography and secondary helper text.
- Retain the established font pairing:
  - UI text: `"Aptos", "Segoe UI Variable", "Segoe UI", sans-serif`
  - data text: `"JetBrains Mono", "Cascadia Code", "Consolas", monospace`
- Extend the existing accent/surface tokens rather than introducing an unrelated theme.

## Implementation Boundaries

Primary files:

- `src/server_monitor/dashboard/static/index.html`
- `src/server_monitor/dashboard/static/app.js`
- `src/server_monitor/dashboard/static/styles.css`
- `tests/dashboard/test_static_routes.py`
- `tests/dashboard/test_static_app_behavior.py`

This should remain a frontend-only refactor. No backend Python changes are required.

## Testing Strategy

- Extend static-route assertions for the new settings workspace hooks and premium visual classes.
- Extend behavior tests for sticky-footer state hooks and other client-side rendering changes that can be validated without a browser automation stack.
- Run:
  - `uv run pytest -q`
  - `uv run ruff check .`
- Perform a manual browser pass on a non-conflicting local port.

## Success Criteria

- The monitor feels more premium without reducing scanability.
- Summary metrics and bars always communicate utilization via semantic color.
- GPU heat cues are clearer, but remain local to GPU contexts.
- The Settings tab uses an always-open add card, a left overview rail, and a right focused editor canvas.
- The settings editor feels more structured through grouped cards and a sticky action footer with clear save/delete hierarchy.
