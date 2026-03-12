# Metrics Stream Badge Latency Design

## Goal

Remove the duplicated `live` signal on each dashboard card by moving streamed metrics timing onto the existing freshness badges and hiding the redundant metrics command-health chips.

## Current Problem

After agentless metrics streaming landed, `system` and `gpu` command-health summaries started reporting `label: "live"` when the stream was healthy. The dashboard now shows:

- a `LIVE` freshness badge for current data
- a `live` command-health chip for `SYS`
- a `live` command-health chip for `GPU`

This duplicates the same concept in multiple places and makes the card harder to scan.

## Constraints

- Keep `command_health.system` and `command_health.gpu` in the payload for degraded-state notifications and diagnostics.
- Do not invent a fake SSH latency for streamed metrics. The stable numeric timing already available is `sample_interval_ms`, which represents stream cadence.
- Preserve the existing `git` and `clash` command-health strip behavior.

## Recommended Design

### Payload

Pass the runtime's `metrics_stream` status through the normalized dashboard update payload. The frontend only needs:

- `state`
- `sample_interval_ms`

Other existing metrics-stream fields may continue to pass through unchanged for future UI use.

### Badge Rendering

System and GPU freshness badges should render:

- `LIVE 250ms` when:
  - the panel freshness state is `live`
  - the server `metrics_stream.state` is `live`
  - `metrics_stream.sample_interval_ms` is a finite number
- `LIVE` when the panel is live but no interval is available
- `CACHED` for non-live freshness states

This timing is stream cadence, not transport round-trip latency. It is still the most honest numeric signal available for streamed metrics in the current architecture.

### Command Health Strip

When a server is using the metrics stream, do not render `SYS` and `GPU` chips in the command-health strip. Continue rendering `GIT` and `CLASH` chips normally.

The backend command-health payload remains unchanged so:

- notification transitions still observe degraded metrics-stream states
- diagnostics exports still include metrics-stream health summaries

## Data Flow

1. `DashboardRuntime` keeps tracking `_MetricsStreamStatus`, including `state` and `sample_interval_ms`.
2. Runtime includes `metrics_stream` in the broadcast payload.
3. `normalize_server_payload` preserves `metrics_stream`.
4. The frontend reads `update.metrics_stream` while rendering System/GPU freshness badges.
5. The command-health strip filters out stream-backed `system` and `gpu` chips.

## Error Handling

- If `metrics_stream` is missing, malformed, or not live, badges fall back to the current `LIVE`/`CACHED` text.
- If the stream is degraded (`reconnecting`, `connecting`, `stopped`), the badges continue to reflect freshness while notifications still key off `command_health`.
- If `sample_interval_ms` is absent, non-numeric, or zero-like invalid input, omit the appended timing text.

## Testing

Add or update tests to cover:

- runtime payload includes `metrics_stream`
- normalized payload preserves `metrics_stream`
- streamed metrics panels render `LIVE <interval>ms`
- command-health strip hides `SYS` and `GPU` for stream-backed cards
- `GIT` and `CLASH` chips still render
- degraded command-health notifications still use metrics panel summaries
