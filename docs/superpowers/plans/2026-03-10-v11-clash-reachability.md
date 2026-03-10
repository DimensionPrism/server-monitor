# v1.1 Clash Reachability Checks Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace placeholder Clash reachability flags with real authenticated HTTP probes (2xx-only) in the agentless dashboard runtime, including per-server probe URL configuration.

**Architecture:** Extend dashboard server settings with Clash probe URLs, then update runtime status polling to retrieve Clash secret via read-only remote command and run authenticated API/UI probes through the existing Clash status command path. Preserve existing payload shape and cache fallback behavior so UI remains compatible while values become real.

**Tech Stack:** Python 3.12, FastAPI dashboard runtime, dataclass settings store, vanilla JS settings form, pytest.

---

## File Structure

- Modify: `src/server_monitor/dashboard/settings.py`
  - Add per-server Clash probe URL fields and defaults.
  - Persist/load fields in TOML store.
- Modify: `src/server_monitor/dashboard/api.py`
  - Extend server request model and serialization paths with new fields.
- Modify: `src/server_monitor/dashboard/runtime.py`
  - Add secret retrieval helper.
  - Parameterize Clash probe command with URLs + secret auth header.
  - Keep cache/freshness semantics stable.
- Modify: `src/server_monitor/dashboard/static/index.html`
  - Add settings form inputs for Clash API/UI probe URLs.
- Modify: `src/server_monitor/dashboard/static/app.js`
  - Wire add/edit settings forms to read/write Clash URL fields.
- Modify: `tests/dashboard/test_runtime.py`
  - Add secret parsing + clash probe behavior tests.
- Modify: `tests/dashboard/test_settings_store.py`
  - Add load/save/default tests for new settings fields.
- Modify: `tests/dashboard/test_settings_api.py`
  - Add API payload roundtrip tests for new fields.
- Modify: `tests/dashboard/test_static_routes.py`
  - Add static asset assertions for new settings controls/wiring.

## Chunk 1: Settings and API Surface

### Task 1: Add settings model/store support for Clash probe URLs

**Files:**
- Modify: `tests/dashboard/test_settings_store.py`
- Modify: `src/server_monitor/dashboard/settings.py`

- [ ] **Step 1: Write failing settings store tests**

Add tests in `tests/dashboard/test_settings_store.py` for:

```python
def test_settings_store_loads_clash_probe_urls_when_present():
    ...
    assert settings.servers[0].clash_api_probe_url == "http://127.0.0.1:9090/version"
    assert settings.servers[0].clash_ui_probe_url == "http://127.0.0.1:9090/ui"
```

```python
def test_settings_store_applies_default_clash_probe_urls_when_missing():
    ...
    assert settings.servers[0].clash_api_probe_url == "http://127.0.0.1:9090/version"
    assert settings.servers[0].clash_ui_probe_url == "http://127.0.0.1:9090/ui"
```

```python
def test_settings_store_saves_clash_probe_urls():
    ...
    assert "clash_api_probe_url" in written_text
    assert "clash_ui_probe_url" in written_text
```

- [ ] **Step 2: Run tests to verify RED**

Run: `uv run pytest tests/dashboard/test_settings_store.py -q`  
Expected: FAIL with missing attributes/keys.

- [ ] **Step 3: Implement minimal settings/store changes**

In `src/server_monitor/dashboard/settings.py`:

- Add fields to `ServerSettings`:

```python
clash_api_probe_url: str = "http://127.0.0.1:9090/version"
clash_ui_probe_url: str = "http://127.0.0.1:9090/ui"
```

- Update `load()` and `save()` mapping to include both keys.

- [ ] **Step 4: Re-run settings store tests**

Run: `uv run pytest tests/dashboard/test_settings_store.py -q`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/dashboard/test_settings_store.py src/server_monitor/dashboard/settings.py
git commit -m "feat: add clash probe url fields to dashboard settings store"
```

### Task 2: Extend settings API payloads for Clash probe URLs

**Files:**
- Modify: `tests/dashboard/test_settings_api.py`
- Modify: `src/server_monitor/dashboard/api.py`

- [ ] **Step 1: Write failing settings API tests**

Add tests asserting:

```python
assert payload["servers"][0]["clash_api_probe_url"] == "http://127.0.0.1:9090/version"
assert payload["servers"][0]["clash_ui_probe_url"] == "http://127.0.0.1:9090/ui"
```

and POST/PUT request payloads with explicit values are persisted and returned.

- [ ] **Step 2: Run tests to verify RED**

Run: `uv run pytest tests/dashboard/test_settings_api.py -q`  
Expected: FAIL due missing fields in request/response models.

- [ ] **Step 3: Implement minimal API model + serialization updates**

In `src/server_monitor/dashboard/api.py`:

- Add fields to `ServerPayload`.
- Include fields in:
  - `serialize_settings(...)`
  - create/update conversion to `ServerSettings`

- [ ] **Step 4: Re-run settings API tests**

Run: `uv run pytest tests/dashboard/test_settings_api.py -q`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/dashboard/test_settings_api.py src/server_monitor/dashboard/api.py
git commit -m "feat: expose clash probe url fields in settings api"
```

## Chunk 2: Agentless Runtime Clash Reachability

### Task 3: Add secret parsing and parameterized Clash probe command

**Files:**
- Modify: `tests/dashboard/test_runtime.py`
- Modify: `src/server_monitor/dashboard/runtime.py`

- [ ] **Step 1: Write failing runtime unit tests for helpers**

Add helper-level tests in `tests/dashboard/test_runtime.py`:

```python
def test_extract_clash_secret_parses_chinese_label_output():
    from server_monitor.dashboard.runtime import _extract_clash_secret
    text = "😼 当前密钥：mysecret"
    assert _extract_clash_secret(text) == "mysecret"
```

```python
def test_clash_command_includes_bearer_header_for_api_and_ui():
    from server_monitor.dashboard.runtime import _clash_command
    cmd = _clash_command("http://127.0.0.1:9090/version", "http://127.0.0.1:9090/ui", "mysecret")
    assert "Authorization: Bearer mysecret" in cmd
```

- [ ] **Step 2: Run targeted tests to verify RED**

Run: `uv run pytest tests/dashboard/test_runtime.py -k "clash and (secret or command)" -q`  
Expected: FAIL (missing helper/function signature mismatch).

- [ ] **Step 3: Implement helper + command signature changes**

In `src/server_monitor/dashboard/runtime.py`:

- Add secret extraction helper:

```python
def _extract_clash_secret(output: str) -> str | None:
    ...
```

- Update command builder:

```python
def _clash_command(api_probe_url: str, ui_probe_url: str, secret: str) -> str:
    ...
```

- Include Bearer header for both API and UI probes.
- Keep 2xx-only logic in command output keys (`api_reachable`, `ui_reachable`).

- [ ] **Step 4: Re-run targeted runtime tests**

Run: `uv run pytest tests/dashboard/test_runtime.py -k "clash and (secret or command)" -q`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/dashboard/test_runtime.py src/server_monitor/dashboard/runtime.py
git commit -m "feat: add secret parsing and authenticated clash probe command"
```

### Task 4: Integrate secret retrieval into status polling flow

**Files:**
- Modify: `tests/dashboard/test_runtime.py`
- Modify: `src/server_monitor/dashboard/runtime.py`

- [ ] **Step 1: Write failing integration-style runtime tests**

Add tests covering:

```python
@pytest.mark.asyncio
async def test_runtime_clash_probe_uses_secret_command_each_status_cycle():
    ...
    assert any("clashsecret" in call[1] for call in executor.calls)
```

```python
@pytest.mark.asyncio
async def test_runtime_clash_probe_sets_unreachable_when_secret_unavailable():
    ...
    assert payload["clash"]["api_reachable"] is False
    assert payload["clash"]["ui_reachable"] is False
    assert payload["clash"]["message"] == "secret-unavailable"
```

Use fake executor behavior branches to emulate success/failure of `clashsecret` and `curl`.

- [ ] **Step 2: Run targeted tests to verify RED**

Run: `uv run pytest tests/dashboard/test_runtime.py -k "clash and (status_cycle or unavailable)" -q`  
Expected: FAIL with current placeholder/no-secret behavior.

- [ ] **Step 3: Implement runtime polling integration**

In `_poll_server(...)` Clash status branch:

- Run secret command first (`clashsecret`).
- Parse via `_extract_clash_secret`.
- If no secret, set Clash values/message and continue gracefully.
- If secret exists, run `_clash_command(server.clash_api_probe_url, server.clash_ui_probe_url, secret)`.

Preserve existing:

- status cadence behavior
- clash cache fallback on command failure
- freshness tracking behavior

- [ ] **Step 4: Re-run targeted runtime tests**

Run: `uv run pytest tests/dashboard/test_runtime.py -k "clash" -q`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/dashboard/test_runtime.py src/server_monitor/dashboard/runtime.py
git commit -m "feat: run secret-aware clash reachability checks in agentless runtime"
```

## Chunk 3: Settings UI Wiring

### Task 5: Add UI controls and form payload wiring for probe URLs

**Files:**
- Modify: `tests/dashboard/test_static_routes.py`
- Modify: `src/server_monitor/dashboard/static/index.html`
- Modify: `src/server_monitor/dashboard/static/app.js`

- [ ] **Step 1: Write failing static asset tests**

Add assertions in `tests/dashboard/test_static_routes.py`:

```python
assert "new-clash-api-probe-url" in html_response.text
assert "new-clash-ui-probe-url" in html_response.text
assert "clash_api_probe_url" in js_response.text
assert "clash_ui_probe_url" in js_response.text
```

- [ ] **Step 2: Run tests to verify RED**

Run: `uv run pytest tests/dashboard/test_static_routes.py -q`  
Expected: FAIL on missing input IDs and JS wiring.

- [ ] **Step 3: Implement minimal HTML + JS wiring**

In `index.html`:

- Add add-server form inputs:
  - Clash API probe URL
  - Clash UI probe URL

In `app.js`:

- Include new fields in add-server payload.
- In `serverEditorTemplate`, add editable inputs.
- In save handler, include both fields in PUT payload.
- Ensure defaults are shown if missing.

- [ ] **Step 4: Re-run static tests**

Run: `uv run pytest tests/dashboard/test_static_routes.py -q`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/dashboard/test_static_routes.py src/server_monitor/dashboard/static/index.html src/server_monitor/dashboard/static/app.js
git commit -m "feat: add clash probe url controls to settings ui"
```

## Chunk 4: Full Verification and Completion Evidence

### Task 6: Regression suite + lint verification

**Files:**
- No expected file changes unless regressions surface

- [ ] **Step 1: Run focused dashboard regression suite**

Run:

```bash
uv run pytest tests/dashboard/test_runtime.py tests/dashboard/test_settings_store.py tests/dashboard/test_settings_api.py tests/dashboard/test_static_routes.py -q
```

Expected: PASS.

- [ ] **Step 2: Run full test suite**

Run:

```bash
uv run pytest -q
```

Expected: PASS.

- [ ] **Step 3: Run lint checks**

Run:

```bash
uv run ruff check .
```

Expected: PASS.

- [ ] **Step 4: Commit follow-up fixes only if needed**

```bash
git add <updated files>
git commit -m "fix: address clash reachability regression issues"
```

- [ ] **Step 5: Capture completion evidence**

Summarize with evidence:

- Secret command is called each status cycle for Clash checks.
- API/UI checks are authenticated and 2xx-only.
- Per-server probe URLs are configurable via settings API/UI.
- Final verification command outputs.
