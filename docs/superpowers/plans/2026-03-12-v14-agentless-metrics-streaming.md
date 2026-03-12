# v1.4 Agentless Metrics Streaming Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add true agentless continuous streaming for `system` and `gpu` on every configured server while keeping `git` and `clash` on the existing status poller.

**Architecture:** Add a dedicated metrics-stream subsystem beside the current poll runtime. Each server gets one long-lived SSH process that runs a remote shell loop, emits NDJSON samples for `system` and `gpu`, and feeds those samples back into `DashboardRuntime` so caches, websocket broadcasts, freshness, and command-health summaries stay in the existing payload model. Keep the first version narrow: the stream cadence is an internal constant near `4/sec`, and the existing persisted settings/UI surface stays unchanged.

**Tech Stack:** Python 3.12, asyncio subprocesses and tasks, SSH, POSIX shell sampling commands, FastAPI runtime, pytest, ruff.

---

## File Structure

- Create: `src/server_monitor/dashboard/metrics_stream_protocol.py`
  - Parse one NDJSON sample line into a typed metrics object and expose protocol-level validation helpers.
- Create: `src/server_monitor/dashboard/metrics_stream_command.py`
  - Build the long-lived remote shell command that samples host and GPU metrics and emits NDJSON at a fixed cadence.
- Create: `src/server_monitor/dashboard/metrics_stream_manager.py`
  - Own per-server SSH stream lifecycle, sample delivery callbacks, malformed-line handling, and reconnect backoff.
- Modify: `src/server_monitor/dashboard/runtime.py`
  - Start and stop the stream manager, consume streamed samples, keep `git` and `clash` polling intact, and derive `system`/`gpu` freshness and command health from stream state.
- Modify: `src/server_monitor/dashboard/main.py`
  - Instantiate the metrics stream manager and inject it into `DashboardRuntime`.
- Create: `tests/dashboard/test_metrics_stream_protocol.py`
  - Unit tests for NDJSON parsing and validation failures.
- Create: `tests/dashboard/test_metrics_stream_command.py`
  - Unit tests for the remote shell builder and cadence assumptions.
- Create: `tests/dashboard/test_metrics_stream_manager.py`
  - Unit tests for stream lifecycle, malformed samples, reconnects, and cleanup.
- Modify: `tests/dashboard/test_runtime.py`
  - Integration tests for streamed cache updates, websocket broadcasts, freshness, command health, and coexistence with the status poller.
- Modify: `tests/dashboard/test_app_runtime_hooks.py`
  - Verify app lifespan start/stop still covers the runtime with the new stream dependency in place.
- Modify: `tests/dashboard/test_diagnostics_api.py`
  - Verify diagnostics expose stream state without leaking secrets.
- Modify: `README.md`
  - Document the new streaming behavior, operational limits, and verification workflow.

## Chunk 1: Protocol and Remote Command

### Task 1: Add failing tests for metrics stream sample parsing

**Files:**
- Create: `tests/dashboard/test_metrics_stream_protocol.py`
- Create: `src/server_monitor/dashboard/metrics_stream_protocol.py`

- [ ] **Step 1: Write the failing protocol tests**

Create `tests/dashboard/test_metrics_stream_protocol.py` with tests like:

```python
from server_monitor.dashboard.metrics_stream_protocol import MetricsStreamSample, parse_metrics_stream_line


def test_parse_metrics_stream_line_returns_typed_sample():
    line = (
        '{"sequence":7,"server_time":"2026-03-12T12:00:00+00:00","sample_interval_ms":250,'
        '"cpu_percent":11.0,"memory_percent":22.0,"disk_percent":33.0,'
        '"network_rx_kbps":44.0,"network_tx_kbps":55.0,'
        '"gpus":[{"index":0,"name":"NVIDIA A100","utilization_gpu_percent":70.0,'
        '"memory_used_mib":1024,"memory_total_mib":40960,"temperature_celsius":50.0}]}'
    )

    sample = parse_metrics_stream_line(line)

    assert sample == MetricsStreamSample(
        sequence=7,
        server_time="2026-03-12T12:00:00+00:00",
        sample_interval_ms=250,
        cpu_percent=11.0,
        memory_percent=22.0,
        disk_percent=33.0,
        network_rx_kbps=44.0,
        network_tx_kbps=55.0,
        gpus=[{"index": 0, "name": "NVIDIA A100", "utilization_gpu_percent": 70.0, "memory_used_mib": 1024, "memory_total_mib": 40960, "temperature_celsius": 50.0}],
    )


def test_parse_metrics_stream_line_rejects_malformed_json():
    ...
```

Also add one validation test for a missing required field like `sequence`.

- [ ] **Step 2: Run the protocol tests to verify RED**

Run: `uv run pytest tests/dashboard/test_metrics_stream_protocol.py -q`

Expected: FAIL with import errors because `metrics_stream_protocol.py` does not exist yet.

- [ ] **Step 3: Implement the minimal protocol module**

Create `src/server_monitor/dashboard/metrics_stream_protocol.py` with:

```python
from dataclasses import dataclass


@dataclass(slots=True)
class MetricsStreamSample:
    sequence: int
    server_time: str
    sample_interval_ms: int
    cpu_percent: float
    memory_percent: float
    disk_percent: float
    network_rx_kbps: float
    network_tx_kbps: float
    gpus: list[dict]
```

Also add:

- `MetricsStreamProtocolError`
- `parse_metrics_stream_line(...)`
- small numeric and field validation helpers

- [ ] **Step 4: Re-run the protocol tests**

Run: `uv run pytest tests/dashboard/test_metrics_stream_protocol.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/dashboard/test_metrics_stream_protocol.py src/server_monitor/dashboard/metrics_stream_protocol.py
git commit -m "feat: add metrics stream protocol parser"
```

### Task 2: Add failing tests for the remote stream command builder

**Files:**
- Create: `tests/dashboard/test_metrics_stream_command.py`
- Create: `src/server_monitor/dashboard/metrics_stream_command.py`

- [ ] **Step 1: Write the failing command-builder tests**

Create `tests/dashboard/test_metrics_stream_command.py` with assertions that the built command:

- opens a long-lived shell loop
- samples at roughly `0.25` seconds
- computes network deltas from `/proc/net/dev`
- reads disk usage less frequently than every sample
- queries GPUs with `nvidia-smi --query-gpu=...`
- prints one JSON object per iteration

Example test skeleton:

```python
from server_monitor.dashboard.metrics_stream_command import build_metrics_stream_command


def test_build_metrics_stream_command_contains_sampling_loop():
    command = build_metrics_stream_command(sample_interval_seconds=0.25, disk_interval_seconds=5.0)

    assert "while :" in command
    assert "/proc/net/dev" in command
    assert "nvidia-smi --query-gpu=index,name,utilization.gpu,memory.used,memory.total,temperature.gpu" in command
    assert "sleep 0.25" in command
```

- [ ] **Step 2: Run the command-builder tests to verify RED**

Run: `uv run pytest tests/dashboard/test_metrics_stream_command.py -q`

Expected: FAIL with import errors because `metrics_stream_command.py` does not exist yet.

- [ ] **Step 3: Implement the minimal command builder**

Create `src/server_monitor/dashboard/metrics_stream_command.py` with:

- `DEFAULT_SAMPLE_INTERVAL_SECONDS = 0.25`
- `DEFAULT_DISK_REFRESH_SECONDS = 5.0`
- `build_metrics_stream_command(...)`

The generated shell should:

- keep previous network counters in shell variables
- refresh disk usage on a slower internal cadence
- collect CPU, memory, and GPU data every sample
- emit one NDJSON sample line per loop iteration

Do not require Python on the remote host.

- [ ] **Step 4: Re-run the command-builder tests**

Run: `uv run pytest tests/dashboard/test_metrics_stream_command.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/dashboard/test_metrics_stream_command.py src/server_monitor/dashboard/metrics_stream_command.py
git commit -m "feat: add metrics stream command builder"
```

## Chunk 2: Stream Lifecycle Manager

### Task 3: Add failing tests for steady-state sample delivery

**Files:**
- Create: `tests/dashboard/test_metrics_stream_manager.py`
- Create: `src/server_monitor/dashboard/metrics_stream_manager.py`

- [ ] **Step 1: Write the failing stream-manager tests**

Create `tests/dashboard/test_metrics_stream_manager.py` with fake subprocesses and tests that verify:

- one stream task starts per configured server
- one SSH process is created per alias
- each NDJSON line triggers the sample callback
- samples preserve server association

Example test skeleton:

```python
@pytest.mark.asyncio
async def test_metrics_stream_manager_delivers_samples_to_callback():
    samples = []

    async def _on_sample(server_id, sample):
        samples.append((server_id, sample.sequence))

    manager = MetricsStreamManager(
        process_factory=_fake_factory(...),
        on_sample=_on_sample,
        on_state_change=_noop_state_change,
    )

    await manager.start([server])

    assert samples == [("srv-a", 1), ("srv-a", 2)]
```

- [ ] **Step 2: Run the stream-manager tests to verify RED**

Run: `uv run pytest tests/dashboard/test_metrics_stream_manager.py -q`

Expected: FAIL because `metrics_stream_manager.py` does not exist yet.

- [ ] **Step 3: Implement the minimal stream manager**

Create `src/server_monitor/dashboard/metrics_stream_manager.py` with:

- `MetricsStreamManager`
- per-server `asyncio.Task` ownership
- one `ssh <alias> sh -lc <stream-command>` process per server
- `on_sample(server_id, sample)` callback support
- `start(servers)` and `stop()` lifecycle methods

Keep the first pass simple: one read loop per server and direct callback delivery.

- [ ] **Step 4: Re-run the stream-manager tests**

Run: `uv run pytest tests/dashboard/test_metrics_stream_manager.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/dashboard/test_metrics_stream_manager.py src/server_monitor/dashboard/metrics_stream_manager.py
git commit -m "feat: add metrics stream manager"
```

### Task 4: Add failing tests for malformed samples, reconnects, and cleanup

**Files:**
- Modify: `tests/dashboard/test_metrics_stream_manager.py`
- Modify: `src/server_monitor/dashboard/metrics_stream_manager.py`

- [ ] **Step 1: Extend the stream-manager tests for failure handling**

Add tests that verify:

- one malformed JSON line is dropped without restarting the stream immediately
- repeated malformed lines trigger a reconnect
- EOF triggers reconnect with bounded backoff
- `stop()` kills child processes and prevents another reconnect cycle

- [ ] **Step 2: Run the targeted failure-handling tests to verify RED**

Run: `uv run pytest tests/dashboard/test_metrics_stream_manager.py -k "malformed or reconnect or stop" -q`

Expected: FAIL because the manager does not yet track parse failures or reconnect backoff.

- [ ] **Step 3: Implement the failure-handling path**

Update `src/server_monitor/dashboard/metrics_stream_manager.py` to add:

- bounded reconnect delays of `1s`, `2s`, then `5s`
- a small consecutive-parse-failure threshold before restart
- state-change callbacks like `live`, `reconnecting`, and `stopped`
- explicit process cleanup on shutdown and restart

- [ ] **Step 4: Re-run the targeted failure-handling tests**

Run: `uv run pytest tests/dashboard/test_metrics_stream_manager.py -k "malformed or reconnect or stop" -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/dashboard/test_metrics_stream_manager.py src/server_monitor/dashboard/metrics_stream_manager.py
git commit -m "feat: harden metrics stream reconnect handling"
```

## Chunk 3: Runtime Integration

### Task 5: Add failing runtime tests for streamed metrics updates

**Files:**
- Modify: `tests/dashboard/test_runtime.py`
- Modify: `tests/dashboard/test_app_runtime_hooks.py`
- Modify: `src/server_monitor/dashboard/runtime.py`
- Modify: `src/server_monitor/dashboard/main.py`

- [ ] **Step 1: Write the failing runtime tests for stream-driven updates**

Add tests that verify:

- `DashboardRuntime.start()` starts the metrics stream manager
- streamed samples update the system and GPU caches immediately
- websocket broadcasts happen from streamed samples without waiting for the status poll cadence
- the status poller still handles only `git` and `clash`

Use a fake stream manager that invokes the runtime callback with a sample like:

```python
sample = MetricsStreamSample(
    sequence=1,
    server_time="2026-03-12T12:00:00+00:00",
    sample_interval_ms=250,
    cpu_percent=11.0,
    memory_percent=22.0,
    disk_percent=33.0,
    network_rx_kbps=44.0,
    network_tx_kbps=55.0,
    gpus=[{"index": 0, "name": "NVIDIA A100", "utilization_gpu_percent": 70.0, "memory_used_mib": 1024, "memory_total_mib": 40960, "temperature_celsius": 50.0}],
)
```

- [ ] **Step 2: Run the targeted runtime tests to verify RED**

Run: `uv run pytest tests/dashboard/test_runtime.py -k "metrics_stream" -q`

Expected: FAIL because the runtime still polls `system` and `gpu` instead of accepting streamed samples.

- [ ] **Step 3: Implement runtime wiring for the stream manager**

Update `src/server_monitor/dashboard/runtime.py` and `src/server_monitor/dashboard/main.py` to:

- inject a `metrics_stream_manager`
- start and stop it with the runtime lifecycle
- add runtime callbacks that merge streamed samples into the existing cache model
- broadcast normalized payloads immediately on streamed updates
- skip the old `system` and `gpu` SSH poll path when streaming is active

- [ ] **Step 4: Re-run the targeted runtime tests**

Run: `uv run pytest tests/dashboard/test_runtime.py -k "metrics_stream" -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/dashboard/test_runtime.py tests/dashboard/test_app_runtime_hooks.py src/server_monitor/dashboard/runtime.py src/server_monitor/dashboard/main.py
git commit -m "feat: wire metrics streaming into dashboard runtime"
```

### Task 6: Add failing runtime and diagnostics tests for cached fallback and stream health

**Files:**
- Modify: `tests/dashboard/test_runtime.py`
- Modify: `tests/dashboard/test_diagnostics_api.py`
- Modify: `src/server_monitor/dashboard/runtime.py`

- [ ] **Step 1: Write the failing tests for disconnect behavior and diagnostics**

Add tests that verify:

- a disconnect keeps the last good `system` and `gpu` sample visible
- freshness flips to `cached` after the grace window instead of zeroing the card
- `command_health.system` and `command_health.gpu` are derived from stream state, not SSH latency numbers
- `build_diagnostics_bundle()` includes a per-server metrics-stream section with connection state, last sample timestamps, and reconnect counters

- [ ] **Step 2: Run the targeted fallback and diagnostics tests to verify RED**

Run: `uv run pytest tests/dashboard/test_runtime.py -k "metrics_stream_cached or metrics_stream_health" -q`

Run: `uv run pytest tests/dashboard/test_diagnostics_api.py -k "metrics_stream" -q`

Expected: FAIL because runtime does not yet track stream state or expose it in diagnostics.

- [ ] **Step 3: Implement stream-backed freshness, command health, and diagnostics**

Update `src/server_monitor/dashboard/runtime.py` to:

- track per-server stream state such as `live`, `reconnecting`, `cached`, and `stopped`
- synthesize `system` and `gpu` command-health summaries from that state
- use sample timestamps and a short grace window to build freshness
- extend diagnostics output with redaction-safe stream metadata

Keep `git` and `clash` diagnostics unchanged.

- [ ] **Step 4: Re-run the targeted fallback and diagnostics tests**

Run: `uv run pytest tests/dashboard/test_runtime.py -k "metrics_stream_cached or metrics_stream_health" -q`

Run: `uv run pytest tests/dashboard/test_diagnostics_api.py -k "metrics_stream" -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/dashboard/test_runtime.py tests/dashboard/test_diagnostics_api.py src/server_monitor/dashboard/runtime.py
git commit -m "feat: expose metrics stream health and cached fallback"
```

## Chunk 4: Documentation and Verification

### Task 7: Document the new streaming behavior and run verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update the README**

Document:

- `system` and `gpu` now use an agentless continuous SSH stream
- `git` and `clash` still use the status poller
- the target cadence is roughly `4/sec`
- the first version keeps cadence internal rather than exposing a new settings field
- expected reconnect and cached-fallback behavior
- how to verify stream health in `/api/diagnostics`

- [ ] **Step 2: Run the focused regression suite**

Run:

```bash
uv run pytest tests/dashboard/test_metrics_stream_protocol.py tests/dashboard/test_metrics_stream_command.py tests/dashboard/test_metrics_stream_manager.py tests/dashboard/test_runtime.py tests/dashboard/test_diagnostics_api.py tests/dashboard/test_app_runtime_hooks.py -q
```

Expected: PASS.

- [ ] **Step 3: Run lint**

Run: `uv run ruff check src/server_monitor/dashboard tests/dashboard`

Expected: PASS.

- [ ] **Step 4: Do a live dashboard check**

Run the dashboard and confirm:

- `/api/diagnostics` returns `200`
- each configured server exposes a live metrics-stream entry
- `system` and `gpu` cards update several times per second
- `git` and `clash` continue updating on their slower poll cadence

- [ ] **Step 5: Commit**

```bash
git add README.md tests/dashboard/test_metrics_stream_protocol.py tests/dashboard/test_metrics_stream_command.py tests/dashboard/test_metrics_stream_manager.py tests/dashboard/test_runtime.py tests/dashboard/test_diagnostics_api.py tests/dashboard/test_app_runtime_hooks.py src/server_monitor/dashboard/metrics_stream_protocol.py src/server_monitor/dashboard/metrics_stream_command.py src/server_monitor/dashboard/metrics_stream_manager.py src/server_monitor/dashboard/runtime.py src/server_monitor/dashboard/main.py
git commit -m "feat: add agentless metrics streaming"
```
