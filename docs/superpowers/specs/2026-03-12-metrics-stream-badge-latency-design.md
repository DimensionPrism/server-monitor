# Metrics Stream Badge Latency Design

## Status

Superseded by follow-up UX/runtime fixes on 2026-03-13. Keep this file as historical context; current behavior is documented below.

## Goal

Keep streamed metrics cards easy to scan while preserving explicit health visibility for `SYS`/`GPU` in the command-health strip.

## Current Problem

After agentless metrics streaming landed, `system` and `gpu` command-health summaries initially reported a non-informative `label: "live"` when the stream was healthy. That provided poor operator signal because:

- the card already had `LIVE` freshness badges
- `live` chip text did not quantify transport behavior

## Constraints

- Keep `command_health.system` and `command_health.gpu` in payloads for degraded-state notifications and diagnostics.
- Do not invent one-shot SSH latency for streamed metrics.
- Preserve the existing command-health strip behavior across enabled panels.

## Recommended Design

### Payload

Pass the runtime's `metrics_stream` status through the normalized dashboard update payload. The frontend only needs:

- `state`
- `sample_interval_ms`
- `transport_latency_ms`

Other existing metrics-stream fields may continue to pass through unchanged for future UI use.

### Badge Rendering

System and GPU freshness badges should render:

- `LIVE` when panel freshness is live
- `CACHED` for non-live freshness states

Do not append stream cadence text to freshness badges.

### Command Health Strip

Keep `SYS`, `GPU`, `GIT`, and `CLASH` chips visible whenever their panels are enabled.

For stream-backed `SYS`/`GPU`:

- healthy state should show transport latency labels (for example `36ms`) when available
- degraded stream states should use explicit labels such as `reconnecting`, `connecting`, and `stopped`
- details/tooltips should identify stream transport context

The backend command-health payload remains unchanged so:

- notification transitions still observe degraded metrics-stream states
- diagnostics exports still include metrics-stream health summaries

## Data Flow

1. `DashboardRuntime` keeps tracking `_MetricsStreamStatus`, including `state` and `sample_interval_ms`.
2. Runtime includes `metrics_stream` in the broadcast payload.
3. `normalize_server_payload` preserves `metrics_stream`.
4. The frontend renders System/GPU freshness as plain `LIVE`/`CACHED`.
5. The command-health strip renders all enabled chips, including stream-backed `system` and `gpu`.

## Error Handling

- If `metrics_stream` is missing, malformed, or not live, badges continue to use freshness-only `LIVE`/`CACHED` text.
- If the stream is degraded (`reconnecting`, `connecting`, `stopped`), the badges continue to reflect freshness while notifications still key off `command_health`.
- If transport latency cannot be computed safely, command-health labels fall back to `--` while preserving stream-state semantics.

## Testing

Add or update tests to cover:

- runtime payload includes `metrics_stream`
- normalized payload preserves `metrics_stream`
- streamed metrics panel badges render plain `LIVE`/`CACHED` without appended cadence text
- command-health strip keeps `SYS` and `GPU` chips visible for stream-backed cards
- `GIT` and `CLASH` chips still render in order
- degraded command-health notifications still use metrics panel summaries
