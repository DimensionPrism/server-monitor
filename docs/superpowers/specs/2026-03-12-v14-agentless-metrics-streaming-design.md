# v1.4 Agentless Metrics Streaming Design

## Summary

The next dashboard backend change should make `system` and `gpu` feel truly live without introducing a remote agent.

The current dashboard already has the right high-level shape for this:

- `git` and `clash` are relatively slow-changing panels and work well on the current status poller
- `system` and `gpu` are the only panels that need higher cadence
- the backend already has websocket broadcasting, per-server caches, freshness metadata, and SSH transport reuse

The design should therefore split the backend into two update paths:

1. a continuous agentless metrics stream for `system` and `gpu`
2. the existing polled path for `git` and `clash`

This keeps the new complexity narrowly scoped to the panels that benefit from it.

## Context

### Current Behavior

Today the dashboard pushes websocket updates, but `system` and `gpu` are still snapshot metrics:

- metrics interval is configured at `1.0s` in `config/servers.toml`
- the runtime batches `system` and `gpu` into one SSH round trip per server
- status panels (`git`, `clash`) use a separate slower cadence

This is fast enough for normal monitoring, but it is still polling. It is not true continuous telemetry.

### User Constraints

The target behavior is now clear:

- stay agentless
- stream both `system` and `gpu`
- target stable `2-4` updates per second
- stream for every configured server, not just the currently expanded card

### Existing Integration Seams

The current codebase already has useful boundaries:

- `DashboardRuntime` owns cache updates, freshness, and websocket broadcasts
- `WebSocketHub` already broadcasts normalized payloads
- `PersistentBatchTransport` already keeps long-lived SSH shells alive for request/response batch polling
- `normalize_server_payload` and the frontend already consume live websocket updates

The design should reuse these seams instead of inventing a second dashboard delivery model.

## Scope

### In Scope

- Agentless continuous streaming for `system` and `gpu`
- One long-lived SSH metrics stream per configured server
- Incremental parsing of streamed metric samples
- Reconnect and backoff behavior for dropped streams
- Freshness and command-health updates for streamed metrics
- Tests for stream parsing, reconnect behavior, cache preservation, and runtime integration
- README updates for the new metrics mode

### Out of Scope

- Streaming for `git` or `clash`
- Remote daemon or service installation
- Historical storage or charts
- Browser-side graphing redesign
- Per-user stream subscriptions or selective server activation
- Targeting `10/sec` or higher in the first version

## Requirements

1. The dashboard must stay agentless.
2. `system` and `gpu` must update continuously for every configured server while the dashboard backend is running.
3. The target steady-state cadence is `2-4/sec` per server.
4. `git` and `clash` must remain on the current polled path.
5. If a metrics stream disconnects, the dashboard must keep the last good sample and mark freshness as cached after a short grace window.
6. Metrics stream failures must not stop `git` and `clash` updates.
7. The websocket payload shape consumed by the existing frontend should remain stable.
8. The backend must reconnect metrics streams with bounded backoff and avoid restart storms.
9. A malformed streamed sample must be dropped independently; one bad line should not immediately kill the whole stream.
10. Command health for `system` and `gpu` should reflect stream health and stream cadence rather than one-shot poll latency.

## Recommended Approach

### One Stream Per Server

The recommended design is one long-lived SSH stream per server that emits both `system` and `gpu` samples together.

Why this is the right default:

- lower SSH session count than separate system and GPU streams
- one reconnect path per server instead of two
- one timestamped sample object can update both cards atomically
- better cache consistency between system and GPU fields

Alternatives such as separate streams per metric type are possible, but they double transport and lifecycle complexity without improving the first version enough to justify it.

## Proposed Architecture

### Runtime Split

The backend should have two concurrent subsystems:

- `MetricsStreamManager`
  - owns one long-lived metrics SSH stream per configured server
  - parses streamed metric samples
  - updates system/GPU caches and websocket state
- `DashboardRuntime`
  - keeps orchestrating `git` and `clash` polling
  - owns shared cache/freshness/health summarization
  - coordinates lifecycle start/stop for both polling and streaming components

`DashboardRuntime` should remain the high-level orchestrator rather than letting the streaming code update the frontend directly.

### Data Flow

For each configured server:

1. runtime starts a metrics stream worker
2. worker opens a long-lived SSH shell
3. remote shell runs a metrics loop at about `250-500ms`
4. loop emits one structured sample line per iteration
5. local parser converts each line into a metrics sample object
6. runtime updates caches and broadcasts the normalized payload immediately

The status poller keeps running independently on its existing cadence and merges into the same server payload model.

## Module Boundaries

### `src/server_monitor/dashboard/metrics_stream_protocol.py`

New focused module.

Responsibilities:

- define the stream sample dataclass
- parse one NDJSON line into a typed metrics sample
- validate required fields and field types
- classify malformed lines

This keeps line parsing separate from SSH process management.

### `src/server_monitor/dashboard/metrics_stream_command.py`

New focused module.

Responsibilities:

- build the remote shell command that streams metrics continuously
- keep the shell script readable and testable
- encode cadence and low-cost sampling behavior in one place

This avoids turning `runtime.py` into a shell-script dump.

### `src/server_monitor/dashboard/metrics_stream_manager.py`

New focused module.

Responsibilities:

- create one stream worker per configured server
- open and manage the long-lived SSH process
- read stdout incrementally
- apply reconnect backoff
- surface parsed samples and stream state changes to the runtime

### `src/server_monitor/dashboard/runtime.py`

Remain the orchestration layer.

Responsibilities:

- start and stop the stream manager alongside the status poller
- apply parsed stream samples to caches
- preserve existing payload shape and normalization
- summarize stream health for `system` and `gpu`
- leave `git` and `clash` polling behavior intact

### `src/server_monitor/dashboard/main.py`

Update app wiring only.

Responsibilities:

- build the runtime with both the existing poll executor and the new metrics stream manager

## Stream Protocol

### Format

Use newline-delimited JSON, one object per sample.

Each sample should include:

- `sequence`
- `server_time`
- `sample_interval_ms`
- `cpu_percent`
- `memory_percent`
- `disk_percent`
- `network_rx_kbps`
- `network_tx_kbps`
- `gpus`

The GPU payload should remain compatible with the existing frontend shape:

- `index`
- `name`
- `utilization_gpu`
- `memory_used_mb`
- `memory_total_mb`
- `temperature_c`

### Why NDJSON

NDJSON is the right fit here because it is:

- easy to parse incrementally
- robust against partial reads
- easy to inspect in logs
- simple to recover from after one malformed sample

The protocol should be text-only and shell-friendly so it works over plain SSH without requiring Python on the remote host.

## Remote Sampling Strategy

### Cadence

The initial target should be about `4/sec`.

The remote loop should sleep for roughly `0.25s` between iterations. The exact observed cadence can vary with SSH and host load, which is acceptable as long as it remains stable and close to target.

### Cost Control

Not every field should be recomputed at full cadence.

Recommended behavior:

- CPU percent: every sample
- memory percent: every sample
- GPU snapshot: every sample
- network rates: every sample, using in-loop deltas from `/proc/net/dev`
- disk usage: cached for a few seconds inside the remote loop instead of recomputing every `250ms`

This keeps the stream responsive without doing unnecessary work.

### Remote Loop Shape

The remote shell loop should:

1. initialize previous CPU and network counters
2. initialize a cached disk value with a refresh timestamp
3. collect `nvidia-smi` output each iteration
4. emit one JSON line with all current fields
5. sleep for the target interval

The first version should prefer POSIX shell plus common Linux tools already assumed by the project.

## Stream Health and Freshness

### Freshness

When samples are arriving normally:

- `system` freshness is `LIVE`
- `gpu` freshness is `LIVE`

If the stream stops:

- keep the last good sample visible
- mark freshness as `CACHED` after a short grace window
- preserve the last update timestamp

### Command Health

For streamed metrics, command health should stop pretending that the dashboard is still measuring one-shot SSH latency.

Instead, the summary should reflect stream state:

- healthy while samples are flowing
- retrying while reconnecting
- failed or cooldown-like state only after sustained reconnect problems

The healthy label can be stream-oriented, for example based on recent sample cadence rather than command duration.

The diagnostics bundle should still include enough evidence to explain:

- last sample time
- recent reconnect attempts
- recent parse drops
- current stream state per server

## Failure Handling

### Disconnects

If a stream exits or the SSH connection drops:

1. mark the worker as disconnected
2. preserve the last cached metrics sample
3. reconnect with bounded backoff, such as `1s -> 2s -> 5s`
4. continue trying until runtime shutdown

### Malformed Samples

One malformed line should not immediately kill the stream.

Recommended behavior:

- drop the malformed sample
- increment a per-stream parse error counter
- only restart the stream after repeated consecutive malformed samples

This protects against one-off partial writes or remote command glitches.

### Browser Backpressure

At `2-4/sec` the UI should usually keep up, but the backend should still coalesce sensibly.

Recommended behavior:

- always keep the latest sample in cache
- websocket broadcasts can drop intermediate samples if a slower consumer falls behind
- never queue unbounded per-sample history in memory

## Testing Strategy

### Unit Tests

- parse valid NDJSON sample lines
- reject malformed lines and missing fields
- build the remote stream command with the expected cadence and fields
- reconnect behavior after EOF
- restart after repeated malformed samples

### Runtime Tests

- runtime updates system/GPU caches from streamed samples
- streamed metrics do not block `git` and `clash` polling
- freshness flips from live to cached after a stream gap
- last good sample survives disconnects
- reconnect resumes updates on the same server

### Live Verification

After implementation:

1. run targeted dashboard tests
2. start the dashboard against the real server config
3. observe `system` and `gpu` updates arriving several times per second
4. confirm `git` and `clash` remain on their existing slower cadence
5. inspect `/api/diagnostics` for stream-state evidence

## Risks and Mitigations

### Risk: Shell-based streaming loop becomes brittle

Mitigation:

- isolate the shell builder in its own module
- keep the wire format NDJSON and easy to inspect
- cover the parser and builder with direct tests

### Risk: Per-server stream workers complicate runtime lifecycle

Mitigation:

- keep stream lifecycle in a dedicated manager
- let `DashboardRuntime` remain the single owner of app-level start/stop

### Risk: Metrics become noisy at higher cadence

Mitigation:

- start at `2-4/sec`, not `10/sec`
- cache slow-changing values such as disk usage inside the remote loop
- expose cadence in diagnostics so tuning is evidence-based

## Recommendation

Implement agentless continuous metrics streaming in one feature branch with two milestones:

1. add the stream protocol, command builder, and per-server stream manager
2. integrate stream state into runtime freshness, health summaries, and live websocket updates

This delivers true live `system` and `gpu` behavior for all configured servers while keeping the rest of the dashboard architecture stable.
