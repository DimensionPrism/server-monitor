# v1.2 Command Health Strip Design

## Summary

The next `v1.2` slice should surface the new backend command telemetry directly in the monitor card.

`v1.2 phase 1` already added retry, cooldown, and recent command health recording in the runtime, but the dashboard still only shows freshness and panel data. That leaves the operator unable to see whether the poller is healthy, retrying, cooling down, or repeatedly failing without opening diagnostics.

This slice adds a compact always-visible health strip to each server card so the dashboard can show per-panel command latency when healthy and concise degraded state when not.

The strip should:

- live in the card body directly under the server header
- always render one chip per enabled panel command
- show latency-only text for healthy commands
- switch to state-only text for degraded commands
- reuse the runtime's recent command journal rather than polling diagnostics from the browser

## Scope

### In Scope

- Server-card command health strip in the monitor UI
- Runtime summary data for `system`, `gpu`, `git`, and `clash`
- WebSocket payload extension for card-level command health
- Chip styling, severity color, and tooltip/detail text
- Tests for runtime payload mapping and frontend rendering behavior
- README note describing the new strip at a high level

### Out of Scope

- Desktop/webhook notifications
- User-triggered diagnostics export action
- Historical charts or persisted latency history
- Per-repo health chips inside the card-level strip
- Settings to configure strip visibility or thresholds
- New API routes

## Requirements

1. Each server card must render one health chip for every enabled panel: `system`, `gpu`, `git`, `clash`.
2. The strip must remain compact and summary-first:
   - placed under the card header
   - above the existing metrics summary rail
3. Healthy chips must show latency only, for example `182ms`.
4. Degraded chips must not combine latency and state in the same chip text:
   - use text such as `retry x2`, `cooldown`, `failed`, or `--`
5. The strip must still render before history exists:
   - `unknown` state
   - placeholder text such as `--`
6. The browser must not poll `GET /api/diagnostics` to power this strip.
7. The WebSocket payload must carry only a compact UI-safe summary, not the full diagnostics bundle.
8. Chip detail text must remain safe to expose in the browser:
   - no secrets
   - no raw secret-bearing command output
9. Git health must summarize the server-level state across repos rather than rendering one chip per repo.
10. Clash health must reflect the worse of secret-fetch and probe outcomes so the chip represents the actual current bottleneck.

## Proposed Module Boundaries

### `src/server_monitor/dashboard/runtime.py`

Remain the source of truth for live server updates.

Responsibilities:

- summarize recent command journal entries into one UI-safe chip model per panel
- attach `command_health` to each server payload before broadcast
- degrade gracefully to `unknown` summaries if health aggregation cannot be derived

### `src/server_monitor/dashboard/static/app.js`

Render the new strip in the existing server card layout.

Responsibilities:

- render one chip per enabled panel
- display latency-only healthy text
- display state-only degraded text
- expose detail text through `title` or equivalent lightweight affordance

### `src/server_monitor/dashboard/static/styles.css`

Define the visual treatment for the strip and chips.

Responsibilities:

- compact inline strip layout
- healthy / retrying / cooldown / failed / unknown severity styling
- responsive wrapping without overpowering the summary metrics rail

## Data Model

Each normalized server update should include a compact `command_health` object:

```json
{
  "command_health": {
    "system": {
      "state": "healthy",
      "label": "182ms",
      "latency_ms": 182,
      "detail": "Last poll succeeded",
      "updated_at": "2026-03-11T13:20:00Z"
    },
    "gpu": {
      "state": "healthy",
      "label": "244ms",
      "latency_ms": 244,
      "detail": "Last poll succeeded",
      "updated_at": "2026-03-11T13:20:00Z"
    },
    "git": {
      "state": "retrying",
      "label": "retry x2",
      "latency_ms": 601,
      "detail": "One or more repos required retries",
      "updated_at": "2026-03-11T13:19:58Z"
    },
    "clash": {
      "state": "failed",
      "label": "failed",
      "latency_ms": 0,
      "detail": "Secret fetch failed",
      "updated_at": "2026-03-11T13:19:57Z"
    }
  }
}
```

### Chip States

Stable UI states:

- `healthy`
- `retrying`
- `cooldown`
- `failed`
- `unknown`

These are UI states, not one-to-one copies of backend failure classes.

## Mapping Rules

### `system`

Use the latest `CommandKind.SYSTEM` record for the server.

- success with one attempt -> `healthy`
- success with more than one attempt -> `retrying`
- `cooldown_skip` -> `cooldown`
- any non-success terminal failure -> `failed`
- no record -> `unknown`

### `gpu`

Use the latest `CommandKind.GPU` record for the server with the same state mapping as `system`.

### `git`

Aggregate the latest `CommandKind.GIT_STATUS` record for each configured repo on the server.

Rules:

- if any repo is `failed`, the chip is `failed`
- else if any repo is `cooldown`, the chip is `cooldown`
- else if any repo is `retrying`, the chip is `retrying`
- else if all known repos are healthy, the chip is `healthy`
- if no repo has health history yet, the chip is `unknown`

Latency rule:

- for `healthy`, use the highest latest repo latency so the chip reflects worst-case current cost
- for degraded states, keep `latency_ms` available for tooltip/debug context, but chip text remains state-only

Detail rule:

- healthy: `"All repos healthy"`
- retrying: `"One or more repos required retries"`
- cooldown: `"One or more repos are cooling down"`
- failed: `"One or more repos failed"`

### `clash`

Combine the latest `CommandKind.CLASH_SECRET` and `CommandKind.CLASH_PROBE` records for the server.

Rules:

- if secret fetch is failed/cooldown/retrying, use that as the chip state because probe depends on secret availability
- else use the probe state
- if both are absent, use `unknown`

Detail examples:

- `"Secret fetch required retry"`
- `"Probe cooling down"`
- `"Probe failed"`

## UI Rendering Rules

1. The strip renders immediately below the server header.
2. The strip always renders before the summary metrics rail.
3. One chip is rendered for each enabled panel in panel order:
   - `system`
   - `gpu`
   - `git`
   - `clash`
4. Chip label rules:
   - `healthy` -> latency text only, such as `182ms`
   - `retrying` -> `retry xN`
   - `cooldown` -> `cooldown`
   - `failed` -> `failed`
   - `unknown` -> `--`
5. Chip prefix text should stay minimal, for example panel shorthand or full panel label depending on available space.
6. Tooltip/title content should include:
   - panel name
   - detail text
   - last updated time if available
7. The strip should wrap on narrow screens rather than compress into unreadable chips.

## Failure Handling

- If runtime health aggregation throws or finds inconsistent data, emit `unknown` chip summaries rather than failing the full server payload.
- If a panel is disabled for a server, omit that chip entirely.
- If the last healthy latency is unavailable for a degraded state, leave `latency_ms` as `null` or `0`; the chip text still stays state-only.
- Existing freshness badges remain unchanged and continue to answer a different question from command health.

## Testing Strategy

### Runtime

- card payload includes `command_health` for enabled panels
- healthy single-attempt command yields `healthy` and latency label
- successful retry yields `retrying` and `retry xN`
- cooldown skip yields `cooldown`
- terminal failure yields `failed`
- missing history yields `unknown`
- git aggregation prefers the worst repo state
- clash aggregation prefers secret-fetch failure over probe success

### Frontend

- monitor render includes the new strip markup
- enabled panel order is preserved
- healthy chips render latency-only text
- degraded chips render state-only text
- styles include severity hooks for the new states

## Acceptance Criteria

1. Each server card shows a compact health strip under the header.
2. Healthy commands show latency only.
3. Degraded commands show state only.
4. Git and Clash chips summarize multi-command or multi-target behavior correctly.
5. The UI uses WebSocket payload data only and does not query diagnostics for this strip.
6. No secrets or raw secret-bearing text are exposed in the browser.
7. Existing monitor behavior and freshness badges remain intact.
