# Dashboard UI Visual Optimization Design

**Date:** 2026-03-11  
**Status:** Approved

## Goal

Optimize the dashboard visual experience for daily monitoring scanability and clearer settings workflows without changing the backend API or data shape.

## User Priorities

- Daily monitoring scanability is the top priority.
- Settings usability priority order is: add server, server overview, focused editing, then error prevention.
- Typical desktop workload is 1-4 servers visible at once.
- Each monitored server may expose 8+ GPUs.
- The collapsed monitor card must show metrics only.

## Scope

### In Scope

- Summary-first monitor cards with clearer visual hierarchy.
- Metrics-only collapsed server card state.
- Cleaner expanded detail sections for System, GPU, Git, and Clash.
- GPU detail layout that remains readable for 8+ devices.
- Settings workspace refactor into add-first, overview-second, edit-on-demand flow.
- Typography, spacing, color, hover, and focus refinements across the static frontend.

### Out of Scope

- Backend API schema changes.
- New monitoring data sources or new dashboard actions.
- Performance optimization work.
- Fleet-density redesign for 9+ simultaneously visible servers.

## Monitor Layout Model

### Server Board

- Keep the board as a card grid, but tune it for 1-4 visible servers with more spacing and stronger separation between cards.
- Favor recognition and per-server readability over maximum information density.

### Collapsed Server Card

Each server card has three layers:

1. Header with server identity and freshness signal.
2. Summary rail with metrics only.
3. Expandable detail stack beneath the summary.

The always-visible summary rail shows exactly four metric blocks:

- CPU utilization
- Memory utilization
- Disk utilization
- GPU aggregate signal suitable for many-GPU servers (for example peak load plus device count)

Collapsed cards do not show Git repo rows, Clash details, or action buttons.

### Expanded Detail Stack

- Keep semantic `<details><summary>` groups for accessibility and keyboard support.
- Sections remain `System`, `GPU`, `Git`, and `Clash`.
- All detail sections default closed so the summary-first layout stays calm by default.
- Open/closed state still persists across rerenders within the current session.

### GPU Drill-Down

- Treat the GPU panel as the primary drill-down area for GPU-heavy hosts.
- Render GPU items as a cleaner auto-fit tile grid sized for 8+ devices.
- Each tile should surface index/name, utilization, memory use, and temperature with aligned labels and bars so outliers are easy to spot.

## Settings Workspace

### Add Server Panel

- Keep the add-server form at the top of the Settings tab.
- Split it into clearer grouped sections:
  - identity (`server_id`, `ssh_alias`)
  - monitoring targets (`working_dirs`)
  - Clash probe URLs
  - enabled panels
- Use stronger helper text, spacing, and defaults so adding a server feels guided rather than cramped.

### Existing Server Overview

- Replace the current stack of fully expanded editors with a compact overview list first.
- Each server row should summarize:
  - server id
  - SSH alias
  - working directory count
  - enabled panel badges
  - whether Clash probe URLs are configured

### Focused Editor

- Selecting a server row opens a dedicated editor panel below the overview list.
- Only one editor is visible at a time.
- Save remains the primary action.
- Delete remains available but visually separated from save.

### Error Prevention

- Use stronger input padding, focus rings, and grouped controls.
- Keep working directories as multiline input, but make the field visually easier to parse.
- Style Clash probe fields as advanced network settings without changing existing validation or defaults.

## Visual System

- Simplify the page background into a calmer dark field so cards and metrics carry the hierarchy.
- Use elevated solid surfaces for cards and nested panels instead of muddy translucent layering.
- Apply a dual-font system:
  - UI text: `"Aptos", "Segoe UI Variable", "Segoe UI", sans-serif`
  - data text: `"JetBrains Mono", "Cascadia Code", "Consolas", monospace`
- Reserve accent cyan for active, focus, and selected states.
- Keep explicit semantic colors for ok, warning, and failure.
- Increase whitespace between cards, sections, and form groups to improve scanning rhythm.

## Interaction and Accessibility

- Strengthen hover and focus treatment for tabs, buttons, summaries, and form inputs.
- Increase summary hit area size on expandable sections.
- Use subtle transitions for color, border, and lift; avoid motion that changes layout meaningfully.
- Preserve responsive fallback to a single-column mobile layout, but optimize primarily for desktop monitoring.

## Implementation Boundaries

Primary files to change:

- `src/server_monitor/dashboard/static/index.html`
- `src/server_monitor/dashboard/static/app.js`
- `src/server_monitor/dashboard/static/styles.css`
- `tests/dashboard/test_static_routes.py`

No backend Python changes are required for this design.

## Testing Strategy

- Extend static route tests to assert the new summary-first monitor hooks and settings workspace hooks.
- Extend static CSS assertions for the new visual system and layout classes.
- Run:
  - `uv run pytest -q`
  - `uv run ruff check .`
- Perform a manual browser smoke test with:
  - `uv run uvicorn server_monitor.dashboard.main:build_dashboard_app --factory --host 127.0.0.1 --port 8080`

## Success Criteria

- The monitor view is easier to scan at a glance for 1-4 servers.
- Collapsed server cards show metrics only, with details hidden until expanded.
- Expanded GPU detail remains readable for 8+ GPUs.
- Settings clearly separate add, overview, and edit flows.
- The frontend looks more intentional and less cramped without any backend behavior changes.
