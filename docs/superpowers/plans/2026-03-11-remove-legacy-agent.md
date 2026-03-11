# Remove Legacy Agent Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the obsolete per-server agent implementation and leave the repo describing only the current agentless dashboard.

**Architecture:** Move the still-used command runner and parser utilities into dashboard-owned modules, update the active runtime to use them, then delete the unused agent package, dead compatibility files, tests, configs, and legacy docs. Keep behavior stable by pinning the agentless runtime first and verifying the full suite afterward.

**Tech Stack:** Python 3.13, FastAPI, asyncio, pytest, ruff, TOML, Markdown docs.

---

## Chunk 1: Preserve Active Runtime Behavior

### Task 1: Add tests that pin the active agentless utility boundaries

**Files:**
- Modify: `tests/dashboard/test_runtime.py`
- Create: `tests/dashboard/parsers/test_system_parser.py`
- Create: `tests/dashboard/parsers/test_gpu_parser.py`
- Create: `tests/dashboard/parsers/test_git_parser.py`
- Create: `tests/dashboard/parsers/test_clash_parser.py`

- [ ] **Step 1: Write failing tests for dashboard-owned parser imports and current parsing behavior**

Add import and behavior coverage using the current parser expectations so the dashboard package owns the runtime utilities after the move.

- [ ] **Step 2: Run the targeted tests to verify they fail**

Run: `uv run pytest tests/dashboard/test_runtime.py tests/dashboard/parsers -q`
Expected: FAIL because dashboard parser modules do not exist yet

- [ ] **Step 3: Create minimal dashboard parser package and update tests only as needed**

Implement the minimal file structure needed for the new imports while preserving current parser behavior.

- [ ] **Step 4: Re-run the targeted tests to verify they pass**

Run: `uv run pytest tests/dashboard/test_runtime.py tests/dashboard/parsers -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/dashboard/test_runtime.py tests/dashboard/parsers src/server_monitor/dashboard/parsers
git commit -m "test: pin dashboard parser behavior before legacy cleanup"
```

### Task 2: Move shared runtime utilities into dashboard-owned modules

**Files:**
- Create: `src/server_monitor/dashboard/command_runner.py`
- Modify: `src/server_monitor/dashboard/runtime.py`
- Delete: `src/server_monitor/agent/command_runner.py`
- Delete: `src/server_monitor/agent/parsers/__init__.py`
- Delete: `src/server_monitor/agent/parsers/base.py`
- Delete: `src/server_monitor/agent/parsers/system.py`
- Delete: `src/server_monitor/agent/parsers/gpu.py`
- Delete: `src/server_monitor/agent/parsers/git_status.py`
- Delete: `src/server_monitor/agent/parsers/clash.py`
- Modify: `tests/dashboard/test_runtime.py`
- Modify: `tests/dashboard/parsers/test_system_parser.py`
- Modify: `tests/dashboard/parsers/test_gpu_parser.py`
- Modify: `tests/dashboard/parsers/test_git_parser.py`
- Modify: `tests/dashboard/parsers/test_clash_parser.py`

- [ ] **Step 1: Write a failing runtime import test for the dashboard command runner location**

Ensure the active runtime imports only dashboard-owned utility modules.

- [ ] **Step 2: Run the targeted tests to verify they fail**

Run: `uv run pytest tests/dashboard/test_runtime.py tests/dashboard/parsers -q`
Expected: FAIL because runtime still imports `server_monitor.agent.*`

- [ ] **Step 3: Move command runner and parser modules into `server_monitor.dashboard` and update runtime imports**

Keep behavior unchanged; this is a namespace and ownership migration.

- [ ] **Step 4: Re-run the targeted tests to verify they pass**

Run: `uv run pytest tests/dashboard/test_runtime.py tests/dashboard/parsers -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/server_monitor/dashboard/command_runner.py src/server_monitor/dashboard/parsers src/server_monitor/dashboard/runtime.py tests/dashboard/test_runtime.py tests/dashboard/parsers
git add -u src/server_monitor/agent/parsers src/server_monitor/agent/command_runner.py
git commit -m "refactor: move runtime utilities out of legacy agent package"
```

## Chunk 2: Delete Legacy Architecture

### Task 3: Remove unused legacy code and tests

**Files:**
- Delete: `src/server_monitor/agent/__init__.py`
- Delete: `src/server_monitor/agent/api.py`
- Delete: `src/server_monitor/agent/config.py`
- Delete: `src/server_monitor/agent/main.py`
- Delete: `src/server_monitor/agent/runtime.py`
- Delete: `src/server_monitor/agent/snapshot_store.py`
- Delete: `src/server_monitor/agent/collectors/__init__.py`
- Delete: `src/server_monitor/agent/collectors/metrics_collector.py`
- Delete: `src/server_monitor/agent/collectors/repo_clash_collector.py`
- Delete: `src/server_monitor/shared/__init__.py`
- Delete: `src/server_monitor/shared/models.py`
- Delete: `src/server_monitor/shared/types.py`
- Delete: `src/server_monitor/dashboard/poller.py`
- Delete: `src/server_monitor/dashboard/config.py`
- Delete: `tests/agent/test_api.py`
- Delete: `tests/agent/test_collectors.py`
- Delete: `tests/agent/test_command_runner.py`
- Delete: `tests/agent/test_repo_collector_commands.py`
- Delete: `tests/agent/test_runtime_hooks.py`
- Delete: `tests/agent/test_snapshot_store.py`
- Delete: `tests/agent/parsers/test_clash_parser.py`
- Delete: `tests/agent/parsers/test_git_parser.py`
- Delete: `tests/agent/parsers/test_gpu_parser.py`
- Delete: `tests/agent/parsers/test_system_parser.py`
- Delete: `tests/shared/test_models.py`
- Delete: `tests/dashboard/test_poller.py`

- [ ] **Step 1: Write a failing test or search assertion that proves no active imports reference deleted legacy modules**

Use existing dashboard tests or add a small import-focused test where needed.

- [ ] **Step 2: Run targeted tests to verify the failure**

Run: `uv run pytest tests/dashboard -q`
Expected: FAIL while legacy references still exist

- [ ] **Step 3: Delete legacy code and legacy-only tests, then update any remaining active tests**

Remove only the obsolete architecture and dead compatibility files.

- [ ] **Step 4: Re-run dashboard-focused tests to verify they pass**

Run: `uv run pytest tests/dashboard -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add -u src/server_monitor/agent src/server_monitor/shared src/server_monitor/dashboard/poller.py src/server_monitor/dashboard/config.py tests/agent tests/shared tests/dashboard/test_poller.py
git commit -m "refactor: remove legacy agent code and obsolete tests"
```

### Task 4: Remove legacy docs and config examples

**Files:**
- Delete: `config/agent.example.toml`
- Modify: `README.md`
- Delete: `docs/superpowers/plans/2026-03-10-server-monitor-dashboard-v1.md`
- Delete: `docs/superpowers/specs/2026-03-10-server-monitor-dashboard-design.md`

- [ ] **Step 1: Write or adjust a failing documentation expectation test if one exists**

If no doc test exists, use repository search as the verification target for removal of per-server agent setup guidance.

- [ ] **Step 2: Run the verification command to confirm legacy doc references still exist**

Run: `rg -n "agent.example|run a lightweight Python agent|agent endpoint|localhost-only HTTP" README.md config docs`
Expected: finds legacy references before cleanup

- [ ] **Step 3: Remove legacy config/docs and rewrite top-level docs to describe only the agentless dashboard**

Keep historical detail out of the active operator guidance.

- [ ] **Step 4: Re-run the verification command to confirm legacy references are gone**

Run: `rg -n "agent.example|run a lightweight Python agent|agent endpoint|localhost-only HTTP" README.md config docs`
Expected: no matches

- [ ] **Step 5: Commit**

```bash
git add README.md
git add -u config/agent.example.toml docs/superpowers/plans/2026-03-10-server-monitor-dashboard-v1.md docs/superpowers/specs/2026-03-10-server-monitor-dashboard-design.md
git commit -m "docs: remove legacy agent runbook and examples"
```

## Chunk 3: Verification

### Task 5: Run full verification and repo-wide legacy-reference sweep

**Files:**
- Verify only

- [ ] **Step 1: Run the full test suite**

Run: `uv run pytest -q`
Expected: PASS

- [ ] **Step 2: Run lint**

Run: `uv run ruff check .`
Expected: PASS

- [ ] **Step 3: Search for leftover code references to the deleted legacy package**

Run: `rg -n "server_monitor\\.agent|SERVER_MONITOR_AGENT_CONFIG|agent.example|AgentPoller|agent_port" src tests config README.md docs`
Expected: no matches, except the new removal design/plan docs if they intentionally mention historical cleanup

- [ ] **Step 4: Review git diff and summarize any residual intentional references**

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "chore: finalize legacy agent removal"
```

Plan complete and saved to `docs/superpowers/plans/2026-03-11-remove-legacy-agent.md`. Ready to execute?
