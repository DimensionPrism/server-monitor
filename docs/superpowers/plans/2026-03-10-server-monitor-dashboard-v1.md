# Server Monitor Dashboard v1 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local, read-only browser dashboard that monitors two GPU servers (system, GPU, git repos, Clash status) through SSH tunnels with near real-time updates.

**Architecture:** Run a lightweight Python agent on each server (localhost-only HTTP). A local Python dashboard service maintains SSH tunnels to both agents, polls snapshots, normalizes data, and streams updates to a single-page browser UI over WebSocket.

**Tech Stack:** Python 3.12+, `uv`, FastAPI, Uvicorn, asyncio, Pydantic v2, pytest, pytest-asyncio, ruff, mypy (optional), vanilla HTML/CSS/JS.

---

## Execution Rules

- Follow `@superpowers/test-driven-development` strictly: no production code before a failing test.
- Keep commits small and frequent (one task per commit).
- Prefer parser fixtures from real command outputs captured on target servers.
- Use only read-only remote operations in v1.

## Planned File Structure

- `pyproject.toml`: project metadata and dependencies.
- `src/server_monitor/shared/models.py`: shared Pydantic schemas used by agent and dashboard.
- `src/server_monitor/shared/types.py`: enums and typed status codes.
- `src/server_monitor/agent/config.py`: agent configuration loading.
- `src/server_monitor/agent/command_runner.py`: async shell command execution wrapper.
- `src/server_monitor/agent/snapshot_store.py`: in-memory latest snapshot store.
- `src/server_monitor/agent/parsers/*.py`: text parsers for system/GPU/git/Clash outputs.
- `src/server_monitor/agent/collectors/*.py`: periodic collectors using parsers + command runner.
- `src/server_monitor/agent/api.py`: FastAPI endpoints (`/health`, `/snapshot`, `/repos`, `/clash`).
- `src/server_monitor/agent/main.py`: agent app entrypoint.
- `src/server_monitor/dashboard/config.py`: local dashboard config.
- `src/server_monitor/dashboard/ssh_tunnel.py`: SSH tunnel/session lifecycle management.
- `src/server_monitor/dashboard/poller.py`: periodic polling of remote agent endpoints.
- `src/server_monitor/dashboard/normalize.py`: schema normalization across servers.
- `src/server_monitor/dashboard/ws_hub.py`: WebSocket client hub + broadcast.
- `src/server_monitor/dashboard/api.py`: dashboard HTTP + WS endpoints.
- `src/server_monitor/dashboard/main.py`: dashboard app entrypoint.
- `src/server_monitor/dashboard/static/index.html`: single-page UI.
- `src/server_monitor/dashboard/static/app.js`: WebSocket rendering logic.
- `src/server_monitor/dashboard/static/styles.css`: dashboard layout and statuses.
- `config/agent.example.toml`: sample per-server agent config.
- `config/local-dashboard.example.toml`: sample local dashboard config.
- `tests/fixtures/outputs/*`: captured command output fixtures.
- `tests/agent/*`: parser/collector/API tests.
- `tests/dashboard/*`: tunnel/poller/normalizer/WS tests.
- `README.md`: setup and run instructions.

## Chunk 1: Project Foundation and Agent Parsing

### Task 1: Bootstrap project with uv and test tooling

**Files:**
- Create: `pyproject.toml`
- Create: `src/server_monitor/__init__.py`
- Create: `tests/__init__.py`
- Create: `.gitignore`

- [ ] **Step 1: Write failing smoke test for package import**

```python
# tests/test_import_smoke.py
def test_package_import():
    import server_monitor  # noqa: F401
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_import_smoke.py -q`  
Expected: FAIL with `ModuleNotFoundError: No module named 'server_monitor'`

- [ ] **Step 3: Create minimal package structure and dependencies**

Add `src` layout and minimal `pyproject.toml`:

```toml
[project]
name = "server-monitor-codex"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = ["fastapi", "uvicorn", "pydantic>=2", "httpx", "tomli-w", "python-dotenv"]

[tool.pytest.ini_options]
pythonpath = ["src"]
```

- [ ] **Step 4: Re-run test to verify it passes**

Run: `uv run pytest tests/test_import_smoke.py -q`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/server_monitor/__init__.py tests/test_import_smoke.py tests/__init__.py .gitignore
git commit -m "chore: bootstrap uv python project layout"
```

### Task 2: Define shared schemas for snapshots

**Files:**
- Create: `src/server_monitor/shared/models.py`
- Create: `src/server_monitor/shared/types.py`
- Test: `tests/shared/test_models.py`

- [ ] **Step 1: Write failing schema validation tests**

```python
def test_snapshot_requires_server_id():
    from server_monitor.shared.models import ServerSnapshot
    ServerSnapshot.model_validate({"timestamp": "2026-03-10T00:00:00Z"})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/shared/test_models.py::test_snapshot_requires_server_id -q`  
Expected: FAIL due missing model/field validation

- [ ] **Step 3: Implement minimal Pydantic models**

Define models for:
- `SystemMetrics`
- `GpuMetrics` + `GpuProcess`
- `RepoStatus`
- `ClashStatus`
- `ServerSnapshot`

- [ ] **Step 4: Add pass-path test and run full shared model tests**

Run: `uv run pytest tests/shared/test_models.py -q`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/server_monitor/shared/models.py src/server_monitor/shared/types.py tests/shared/test_models.py
git commit -m "feat: add shared snapshot schemas"
```

### Task 3: Build command runner and parser contract

**Files:**
- Create: `src/server_monitor/agent/command_runner.py`
- Create: `src/server_monitor/agent/parsers/base.py`
- Test: `tests/agent/test_command_runner.py`

- [ ] **Step 1: Write failing timeout and non-zero exit tests**

```python
async def test_command_runner_returns_stdout():
    runner = CommandRunner(timeout_seconds=1)
    result = await runner.run(["bash", "-lc", "echo ok"])
    assert result.stdout.strip() == "ok"
```

- [ ] **Step 2: Run tests to verify fail**

Run: `uv run pytest tests/agent/test_command_runner.py -q`  
Expected: FAIL due missing class/module

- [ ] **Step 3: Implement minimal async subprocess runner and result model**

Implement:
- `CommandResult(stdout, stderr, exit_code, duration_ms, error=None)`
- `CommandRunner.run(argv: list[str])`

- [ ] **Step 4: Re-run tests**

Run: `uv run pytest tests/agent/test_command_runner.py -q`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/server_monitor/agent/command_runner.py src/server_monitor/agent/parsers/base.py tests/agent/test_command_runner.py
git commit -m "feat: add async command runner for agent collectors"
```

### Task 4: Implement parser modules with fixture-driven tests

**Files:**
- Create: `src/server_monitor/agent/parsers/system.py`
- Create: `src/server_monitor/agent/parsers/gpu.py`
- Create: `src/server_monitor/agent/parsers/git_status.py`
- Create: `src/server_monitor/agent/parsers/clash.py`
- Create: `tests/fixtures/outputs/*.txt`
- Test: `tests/agent/parsers/test_system_parser.py`
- Test: `tests/agent/parsers/test_gpu_parser.py`
- Test: `tests/agent/parsers/test_git_parser.py`
- Test: `tests/agent/parsers/test_clash_parser.py`

- [ ] **Step 1: Add failing parser tests with fixture inputs**

Example:

```python
def test_parse_nvidia_smi_fixture():
    text = load_fixture("nvidia_smi_query.txt")
    parsed = parse_nvidia_smi(text)
    assert parsed[0].utilization_gpu == 73
```

- [ ] **Step 2: Run parser tests to verify fail**

Run: `uv run pytest tests/agent/parsers -q`  
Expected: FAIL due missing parser functions

- [ ] **Step 3: Implement minimal parser functions to satisfy tests**

Implement pure functions that return structured data and tolerate malformed lines:
- `parse_system_snapshot(...)`
- `parse_gpu_snapshot(...)`
- `parse_repo_status(...)`
- `parse_clash_status(...)`

- [ ] **Step 4: Re-run parser tests**

Run: `uv run pytest tests/agent/parsers -q`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/server_monitor/agent/parsers tests/agent/parsers tests/fixtures/outputs
git commit -m "feat: add fixture-tested parsers for system gpu git and clash"
```

## Chunk 2: Agent API and Local Dashboard Backend

### Task 5: Add snapshot store and periodic collectors

**Files:**
- Create: `src/server_monitor/agent/snapshot_store.py`
- Create: `src/server_monitor/agent/collectors/metrics_collector.py`
- Create: `src/server_monitor/agent/collectors/repo_clash_collector.py`
- Test: `tests/agent/test_snapshot_store.py`
- Test: `tests/agent/test_collectors.py`

- [ ] **Step 1: Write failing tests for store freshness and partial update behavior**

```python
def test_store_retains_last_good_metrics_on_parser_failure():
    ...
```

- [ ] **Step 2: Run tests to verify fail**

Run: `uv run pytest tests/agent/test_snapshot_store.py tests/agent/test_collectors.py -q`  
Expected: FAIL

- [ ] **Step 3: Implement store + collectors with independent error isolation**

Implement:
- atomic update methods per data domain
- collector loop methods that return testable one-shot update function

- [ ] **Step 4: Re-run tests**

Run: `uv run pytest tests/agent/test_snapshot_store.py tests/agent/test_collectors.py -q`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/server_monitor/agent/snapshot_store.py src/server_monitor/agent/collectors tests/agent/test_snapshot_store.py tests/agent/test_collectors.py
git commit -m "feat: add agent snapshot store and collector loops"
```

### Task 6: Implement agent HTTP API

**Files:**
- Create: `src/server_monitor/agent/config.py`
- Create: `src/server_monitor/agent/api.py`
- Create: `src/server_monitor/agent/main.py`
- Create: `config/agent.example.toml`
- Test: `tests/agent/test_api.py`

- [ ] **Step 1: Write failing API contract tests**

```python
def test_snapshot_endpoint_returns_snapshot_shape(client):
    r = client.get("/snapshot")
    assert r.status_code == 200
    assert "server_id" in r.json()
```

- [ ] **Step 2: Run API tests to verify fail**

Run: `uv run pytest tests/agent/test_api.py -q`  
Expected: FAIL

- [ ] **Step 3: Implement FastAPI app and config loader**

Implement endpoints:
- `/health`
- `/snapshot`
- `/repos`
- `/clash`

Bind default host to `127.0.0.1` in startup docs/commands.

- [ ] **Step 4: Re-run API tests**

Run: `uv run pytest tests/agent/test_api.py -q`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/server_monitor/agent/config.py src/server_monitor/agent/api.py src/server_monitor/agent/main.py config/agent.example.toml tests/agent/test_api.py
git commit -m "feat: expose localhost-only read API for server agent"
```

### Task 7: Build SSH tunnel manager and poll scheduler

**Files:**
- Create: `src/server_monitor/dashboard/config.py`
- Create: `src/server_monitor/dashboard/ssh_tunnel.py`
- Create: `src/server_monitor/dashboard/poller.py`
- Test: `tests/dashboard/test_ssh_tunnel.py`
- Test: `tests/dashboard/test_poller.py`

- [ ] **Step 1: Write failing reconnect and poll interval tests**

```python
async def test_tunnel_reconnect_backoff_after_failure():
    ...
```

- [ ] **Step 2: Run tests to verify fail**

Run: `uv run pytest tests/dashboard/test_ssh_tunnel.py tests/dashboard/test_poller.py -q`  
Expected: FAIL

- [ ] **Step 3: Implement minimal tunnel process manager + poll loop**

Implement:
- tunnel lifecycle state machine (`connected`, `reconnecting`, `down`)
- async poll tasks for `/snapshot`, `/repos`, `/clash`

- [ ] **Step 4: Re-run tests**

Run: `uv run pytest tests/dashboard/test_ssh_tunnel.py tests/dashboard/test_poller.py -q`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/server_monitor/dashboard/config.py src/server_monitor/dashboard/ssh_tunnel.py src/server_monitor/dashboard/poller.py tests/dashboard/test_ssh_tunnel.py tests/dashboard/test_poller.py
git commit -m "feat: add dashboard ssh tunnel manager and poll scheduler"
```

### Task 8: Add normalization and WebSocket broadcast layer

**Files:**
- Create: `src/server_monitor/dashboard/normalize.py`
- Create: `src/server_monitor/dashboard/ws_hub.py`
- Create: `src/server_monitor/dashboard/api.py`
- Create: `src/server_monitor/dashboard/main.py`
- Test: `tests/dashboard/test_normalize.py`
- Test: `tests/dashboard/test_ws_hub.py`

- [ ] **Step 1: Write failing normalization and broadcast tests**

```python
def test_normalize_marks_stale_when_timestamp_exceeds_threshold():
    ...
```

- [ ] **Step 2: Run tests to verify fail**

Run: `uv run pytest tests/dashboard/test_normalize.py tests/dashboard/test_ws_hub.py -q`  
Expected: FAIL

- [ ] **Step 3: Implement normalizer and websocket fan-out**

Implement:
- unified payload shape for both servers
- stale/error badge derivation
- WS endpoint `/ws` that pushes periodic updates

- [ ] **Step 4: Re-run tests**

Run: `uv run pytest tests/dashboard/test_normalize.py tests/dashboard/test_ws_hub.py -q`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/server_monitor/dashboard/normalize.py src/server_monitor/dashboard/ws_hub.py src/server_monitor/dashboard/api.py src/server_monitor/dashboard/main.py tests/dashboard/test_normalize.py tests/dashboard/test_ws_hub.py
git commit -m "feat: add normalized payload and websocket streaming api"
```

## Chunk 3: Browser UI, E2E Verification, and Docs

### Task 9: Implement single-page dashboard UI

**Files:**
- Create: `src/server_monitor/dashboard/static/index.html`
- Create: `src/server_monitor/dashboard/static/app.js`
- Create: `src/server_monitor/dashboard/static/styles.css`
- Modify: `src/server_monitor/dashboard/api.py`
- Test: `tests/dashboard/test_static_routes.py`

- [ ] **Step 1: Write failing test for static page and ws bootstrapping**

```python
def test_root_serves_dashboard_html(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Server A" in r.text
```

- [ ] **Step 2: Run test to verify fail**

Run: `uv run pytest tests/dashboard/test_static_routes.py -q`  
Expected: FAIL

- [ ] **Step 3: Implement minimal UI with 4 modules and stale badges**

Sections:
- system metrics
- GPU metrics
- repo table
- Clash status + quick links

- [ ] **Step 4: Re-run tests**

Run: `uv run pytest tests/dashboard/test_static_routes.py -q`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/server_monitor/dashboard/static src/server_monitor/dashboard/api.py tests/dashboard/test_static_routes.py
git commit -m "feat: add single-page monitoring dashboard ui"
```

### Task 10: End-to-end test pass and operator documentation

**Files:**
- Create: `tests/e2e/test_dashboard_flow.py`
- Create: `README.md`
- Create: `config/local-dashboard.example.toml`
- Modify: `pyproject.toml`

- [ ] **Step 1: Write failing e2e-style integration test (mocked upstream agent)**

```python
async def test_dashboard_ws_emits_two_server_payload(async_client):
    ...
```

- [ ] **Step 2: Run test to verify fail**

Run: `uv run pytest tests/e2e/test_dashboard_flow.py -q`  
Expected: FAIL

- [ ] **Step 3: Implement missing glue code and docs**

README must include:
- local setup with `uv sync`
- running agent on servers
- creating SSH tunnels
- running local dashboard
- config examples and expected polling intervals

- [ ] **Step 4: Run full verification suite**

Run:
- `uv run pytest -q`
- `uv run ruff check .`

Expected: all PASS, no lint errors.

- [ ] **Step 5: Commit**

```bash
git add README.md config/local-dashboard.example.toml tests/e2e/test_dashboard_flow.py pyproject.toml
git commit -m "docs: add runbook and finalize v1 integration checks"
```

## Final Verification Checklist

- [ ] All tests written before implementation for each unit (TDD evidence in commit history)
- [ ] Agent binds to localhost only
- [ ] Dashboard reads both servers through SSH tunnel paths
- [ ] Metrics update frequency aligns with v1 requirements
- [ ] Git and Clash status visible for configured repositories/instances
- [ ] Partial failures render degraded state without breaking full dashboard

Plan complete and saved to `docs/superpowers/plans/2026-03-10-server-monitor-dashboard-v1.md`. Ready to execute.

