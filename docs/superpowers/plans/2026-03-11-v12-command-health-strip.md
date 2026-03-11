# v1.2 Command Health Strip Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a compact always-visible per-server command health strip that shows latency for healthy panel commands and concise degraded state for retrying, cooldown, failed, and unknown conditions.

**Architecture:** Extend the runtime's live WebSocket payload with a small `command_health` summary derived from the recent command journal, pass it through normalization unchanged, and render it in the existing server card above the summary metrics rail. Keep the feature read-only and card-level: no new API route, no diagnostics fetch, and no settings surface for this slice.

**Tech Stack:** Python 3.12, FastAPI WebSocket payloads, existing dashboard runtime, vanilla JavaScript, CSS, pytest, ruff.

---

## File Structure

- Modify: `src/server_monitor/dashboard/runtime.py`
  - Summarize recent command health records into UI-safe chip models for `system`, `gpu`, `git`, and `clash`.
- Modify: `src/server_monitor/dashboard/normalize.py`
  - Pass `command_health` through normalized WebSocket payloads.
- Modify: `src/server_monitor/dashboard/static/app.js`
  - Render the compact chip row in server cards with latency-only healthy labels and state-only degraded labels.
- Modify: `src/server_monitor/dashboard/static/styles.css`
  - Add compact strip/chip styles and severity state hooks.
- Modify: `tests/dashboard/test_runtime.py`
  - Cover runtime `command_health` mapping for healthy, retrying, cooldown, failed, unknown, git aggregate, and clash aggregate cases.
- Modify: `tests/dashboard/test_normalize.py`
  - Assert `command_health` passes through normalization.
- Modify: `tests/dashboard/test_static_routes.py`
  - Assert the static assets include the new strip renderer and CSS hooks.
- Modify: `tests/dashboard/test_static_app_behavior.py`
  - Assert rendered cards show the strip, preserve panel order, and follow healthy vs degraded text rules.
- Modify: `README.md`
  - Document the health strip at a high level.

## Chunk 1: Runtime Command Health Summary

### Task 1: Add failing runtime and normalize tests for command health payloads

**Files:**
- Modify: `tests/dashboard/test_runtime.py`
- Modify: `tests/dashboard/test_normalize.py`

- [ ] **Step 1: Add failing normalize pass-through test**

Extend `tests/dashboard/test_normalize.py` with:

```python
def test_normalize_passes_through_command_health():
    from server_monitor.dashboard.normalize import normalize_server_payload

    now = datetime(2026, 3, 11, tzinfo=UTC)
    payload = {
        "timestamp": now.isoformat(),
        "snapshot": {"cpu_percent": 10.0},
        "repos": [],
        "clash": {"running": True},
        "command_health": {
            "system": {
                "state": "healthy",
                "label": "182ms",
                "latency_ms": 182,
                "detail": "Last poll succeeded",
                "updated_at": now.isoformat(),
            }
        },
    }

    normalized = normalize_server_payload(
        server_id="server-a",
        payload=payload,
        now=now,
        stale_after_seconds=10,
    )

    assert normalized["command_health"]["system"]["label"] == "182ms"
```

- [ ] **Step 2: Add failing runtime tests for chip states**

Add targeted tests to `tests/dashboard/test_runtime.py` for:

```python
@pytest.mark.asyncio
async def test_runtime_emits_command_health_latency_for_healthy_system():
    ...
    payload = ws.messages[0]
    assert payload["command_health"]["system"]["state"] == "healthy"
    assert payload["command_health"]["system"]["label"].endswith("ms")


@pytest.mark.asyncio
async def test_runtime_emits_retrying_state_for_successful_retry():
    ...
    assert payload["command_health"]["system"]["state"] == "retrying"
    assert payload["command_health"]["system"]["label"] == "retry x2"


@pytest.mark.asyncio
async def test_runtime_emits_unknown_command_health_before_first_status_history():
    ...
    assert payload["command_health"]["git"]["state"] == "unknown"
    assert payload["command_health"]["git"]["label"] == "--"
```

Also add focused cases for:

- git worst-repo aggregation
- clash secret failure winning over probe success
- cooldown mapping to `cooldown`
- terminal parse/nonzero failure mapping to `failed`

- [ ] **Step 3: Run targeted runtime and normalize tests to verify RED**

Run:

```bash
uv run pytest tests/dashboard/test_runtime.py -k "command_health or retrying or cooldown or clash" -q
uv run pytest tests/dashboard/test_normalize.py -q
```

Expected:

- normalize test fails because `command_health` is not passed through
- runtime tests fail because payloads do not include `command_health`

- [ ] **Step 4: Implement `command_health` pass-through in normalize**

Update `src/server_monitor/dashboard/normalize.py` so normalized payloads include:

```python
"command_health": payload.get("command_health", {}),
```

- [ ] **Step 5: Implement runtime command health summarization**

Add focused helpers in `src/server_monitor/dashboard/runtime.py`:

```python
def _command_health_state_from_record(record: dict | None) -> str:
    ...


def _command_health_label(*, state: str, latency_ms: int | None, attempt_count: int) -> str:
    ...


def _summarize_server_command_health(self, *, server: ServerSettings) -> dict[str, dict]:
    ...
```

Implementation rules:

- `system` and `gpu`: use the latest matching record for `target_label="server"`
- `git`: aggregate latest `git_status` record per configured repo, then select the worst state
- `clash`: compare latest `clash_secret` and `clash_probe` records, preferring secret degradation
- healthy single-attempt success -> `healthy` with latency label
- healthy multi-attempt success -> `retrying` with `retry xN`
- `cooldown_skip` -> `cooldown`
- all other non-success terminal failures -> `failed`
- no relevant history -> `unknown` with label `--`

Attach the computed summary to the server payload before `normalize_server_payload(...)`.

- [ ] **Step 6: Re-run targeted tests**

Run:

```bash
uv run pytest tests/dashboard/test_runtime.py -k "command_health or retrying or cooldown or clash" -q
uv run pytest tests/dashboard/test_normalize.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add tests/dashboard/test_runtime.py tests/dashboard/test_normalize.py src/server_monitor/dashboard/runtime.py src/server_monitor/dashboard/normalize.py
git commit -m "feat: add command health summaries to runtime payloads"
```

## Chunk 2: Monitor Card Health Strip UI

### Task 2: Add failing static asset and app behavior tests for the strip

**Files:**
- Modify: `tests/dashboard/test_static_routes.py`
- Modify: `tests/dashboard/test_static_app_behavior.py`

- [ ] **Step 1: Add failing static route assertions**

Extend `tests/dashboard/test_static_routes.py` with assertions like:

```python
def test_app_js_wires_command_health_strip_renderer():
    ...
    assert "function renderCommandHealthStrip" in response.text
    assert "update.command_health" in response.text
    assert "command-health-chip" in response.text


def test_styles_css_has_command_health_strip_rules():
    ...
    assert ".command-health-strip" in response.text
    assert ".command-health-chip" in response.text
    assert '[data-state="retrying"]' in response.text
```

- [ ] **Step 2: Add failing JS behavior tests**

Extend `tests/dashboard/test_static_app_behavior.py` with cases like:

```python
def test_render_monitor_displays_command_health_strip_for_enabled_panels():
    _run_app_js_test(
        """
        const grid = document.getElementById("monitor-grid");
        globalThis.__querySelectorAll = () => [];

        __testExports.state.updates = new Map([
          [
            "server-a",
            {
              server_id: "server-a",
              enabled_panels: ["system", "git"],
              command_health: {
                system: { state: "healthy", label: "182ms", detail: "ok" },
                git: { state: "failed", label: "failed", detail: "repo failed" },
              },
              freshness: {},
              snapshot: { cpu_percent: 10, memory_percent: 20, disk_percent: 30, gpus: [], metadata: {} },
              repos: [],
              clash: {},
            },
          ],
        ]);

        __testExports.renderMonitor();

        if (!grid.innerHTML.includes("command-health-strip")) {
          throw new Error("missing command health strip");
        }
        if (!grid.innerHTML.includes("182ms")) {
          throw new Error("healthy latency label missing");
        }
        if (!grid.innerHTML.includes(">failed<")) {
          throw new Error("degraded state label missing");
        }
        """
    )
```

Add another test that asserts panel order and ensures healthy chips do not render `ok`.

- [ ] **Step 3: Run targeted static tests to verify RED**

Run:

```bash
uv run pytest tests/dashboard/test_static_routes.py -k "command_health_strip" -q
uv run pytest tests/dashboard/test_static_app_behavior.py -k "command_health_strip or healthy_latency" -q
```

Expected: FAIL because the strip renderer and styles do not exist yet.

- [ ] **Step 4: Implement the strip renderer in `app.js`**

Add helpers in `src/server_monitor/dashboard/static/app.js`:

```javascript
function commandHealthOrder(enabledPanels) {
  return ["system", "gpu", "git", "clash"].filter((panel) => enabledPanels.has(panel));
}

function renderCommandHealthChip(panelName, summary) {
  ...
}

function renderCommandHealthStrip(update, panels) {
  ...
}
```

Render the strip:

- below `.server-card-head`
- above `renderServerSummary(...)`
- using `update.command_health || {}`
- defaulting missing summaries to `{ state: "unknown", label: "--" }`
- keeping chip labels to latency-only healthy text and state-only degraded text

- [ ] **Step 5: Implement strip styling in `styles.css`**

Add compact styles for:

- `.command-health-strip`
- `.command-health-chip`
- `.command-health-chip-label`
- `.command-health-chip-value`
- state hooks via `[data-state="healthy"]`, `[data-state="retrying"]`, `[data-state="cooldown"]`, `[data-state="failed"]`, `[data-state="unknown"]`

Keep the strip visually subordinate to the main summary metrics rail.

- [ ] **Step 6: Re-run targeted static tests**

Run:

```bash
uv run pytest tests/dashboard/test_static_routes.py -k "command_health_strip" -q
uv run pytest tests/dashboard/test_static_app_behavior.py -k "command_health_strip or healthy_latency" -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add tests/dashboard/test_static_routes.py tests/dashboard/test_static_app_behavior.py src/server_monitor/dashboard/static/app.js src/server_monitor/dashboard/static/styles.css
git commit -m "feat: add dashboard command health strip"
```

## Chunk 3: Docs And Full Verification

### Task 3: Document the strip and run the full dashboard test suite

**Files:**
- Modify: `README.md`
- Modify: `tests/dashboard/test_runtime.py`
- Modify: `tests/dashboard/test_normalize.py`
- Modify: `tests/dashboard/test_static_routes.py`
- Modify: `tests/dashboard/test_static_app_behavior.py`
- Modify: `src/server_monitor/dashboard/runtime.py`
- Modify: `src/server_monitor/dashboard/normalize.py`
- Modify: `src/server_monitor/dashboard/static/app.js`
- Modify: `src/server_monitor/dashboard/static/styles.css`

- [ ] **Step 1: Update README**

Add a short bullet to `README.md` in the "What Works Now" section noting that monitor cards now show a command health strip with latency-first healthy state and degraded retry/cooldown/failure state.

- [ ] **Step 2: Run focused dashboard verification**

Run:

```bash
uv run pytest tests/dashboard/test_runtime.py tests/dashboard/test_normalize.py tests/dashboard/test_static_routes.py tests/dashboard/test_static_app_behavior.py -q
```

Expected: PASS.

- [ ] **Step 3: Run full verification**

Run:

```bash
uv run pytest -q
uv run ruff check .
```

Expected:

- pytest passes
- ruff reports `All checks passed!`

- [ ] **Step 4: Commit**

```bash
git add README.md tests/dashboard/test_runtime.py tests/dashboard/test_normalize.py tests/dashboard/test_static_routes.py tests/dashboard/test_static_app_behavior.py src/server_monitor/dashboard/runtime.py src/server_monitor/dashboard/normalize.py src/server_monitor/dashboard/static/app.js src/server_monitor/dashboard/static/styles.css
git commit -m "feat: surface command health in dashboard cards"
```

Plan complete and saved to `docs/superpowers/plans/2026-03-11-v12-command-health-strip.md`. Ready to execute?
