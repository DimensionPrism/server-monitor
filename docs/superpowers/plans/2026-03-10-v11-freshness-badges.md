# v1.1 Freshness Badges Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add explicit `LIVE`/`CACHED` freshness badges for System/GPU/Git/Clash panels and each repo row, replacing the server-level stale line.

**Architecture:** Keep freshness logic backend-owned in `DashboardRuntime` so the websocket payload carries explicit panel and repo freshness states. Frontend reads and renders badges without recomputing freshness rules. Freshness uses hybrid policy (`poll_error` OR age threshold) with panel-specific thresholds derived from polling intervals.

**Tech Stack:** Python 3.12, FastAPI websocket runtime, vanilla JS frontend, pytest.

---

## File Structure

- Modify: `src/server_monitor/dashboard/runtime.py`
  - Add poll-health tracking state for panels and repos.
  - Add helpers to compute panel/repo freshness objects.
  - Attach freshness fields into payload prior to normalization/broadcast.
- Modify: `src/server_monitor/dashboard/normalize.py`
  - Pass through `freshness` as a first-class normalized field.
- Modify: `src/server_monitor/dashboard/static/app.js`
  - Render panel and repo freshness badges.
  - Remove server header stale text.
- Modify: `src/server_monitor/dashboard/static/styles.css`
  - Add freshness badge styles and summary layout helpers.
- Modify: `tests/dashboard/test_runtime.py`
  - Add runtime freshness behavior coverage.
- Modify: `tests/dashboard/test_normalize.py`
  - Assert normalized payload includes freshness object.
- Modify: `tests/dashboard/test_static_routes.py`
  - Assert app.js freshness hooks exist and stale header output is removed.

## Chunk 1: Backend Freshness Computation

### Task 1: Panel freshness payload and poll error behavior

**Files:**
- Modify: `tests/dashboard/test_runtime.py`
- Modify: `src/server_monitor/dashboard/runtime.py`

- [ ] **Step 1: Write failing tests for panel freshness payload**

Add tests to `tests/dashboard/test_runtime.py`:

```python
@pytest.mark.asyncio
async def test_runtime_emits_panel_freshness_live_on_success():
    ...
    payload = ws.messages[0]
    assert payload["freshness"]["system"]["state"] == "live"
    assert payload["freshness"]["gpu"]["state"] == "live"
    assert payload["freshness"]["git"]["state"] == "live"
    assert payload["freshness"]["clash"]["state"] == "live"
```

```python
@pytest.mark.asyncio
async def test_runtime_marks_system_freshness_cached_on_poll_error():
    ...
    payload = ws.messages[0]
    assert payload["freshness"]["system"]["state"] == "cached"
    assert payload["freshness"]["system"]["reason"] == "poll_error"
```

- [ ] **Step 2: Run targeted runtime tests to confirm failure**

Run: `uv run pytest tests/dashboard/test_runtime.py -k "freshness and (panel or system)" -q`  
Expected: FAIL with missing `freshness` keys or assertion mismatches.

- [ ] **Step 3: Implement minimal panel freshness runtime logic**

In `src/server_monitor/dashboard/runtime.py`:

```python
self._system_last_poll_ok: dict[str, bool] = {}
self._gpu_last_poll_ok: dict[str, bool] = {}
self._git_last_poll_ok: dict[str, bool] = {}
self._clash_last_poll_ok: dict[str, bool] = {}
```

On each poll branch, set corresponding `*_last_poll_ok[server_id]` to `True/False`.

Add helper:

```python
def _build_freshness_entry(*, now: datetime, last_updated_at: str | None, last_poll_ok: bool | None, threshold_seconds: float) -> dict:
    ...
```

Attach to payload:

```python
payload["freshness"] = {
    "system": ...,
    "gpu": ...,
    "git": ...,
    "clash": ...,
}
```

- [ ] **Step 4: Re-run targeted runtime tests**

Run: `uv run pytest tests/dashboard/test_runtime.py -k "freshness and (panel or system)" -q`  
Expected: PASS.

- [ ] **Step 5: Commit chunk changes**

Run:

```bash
git add tests/dashboard/test_runtime.py src/server_monitor/dashboard/runtime.py
git commit -m "feat: add panel freshness state to dashboard runtime payload"
```

### Task 2: Repo freshness, age thresholds, and normalization passthrough

**Files:**
- Modify: `tests/dashboard/test_runtime.py`
- Modify: `tests/dashboard/test_normalize.py`
- Modify: `src/server_monitor/dashboard/runtime.py`
- Modify: `src/server_monitor/dashboard/normalize.py`

- [ ] **Step 1: Write failing tests for repo freshness and reason precedence**

Add tests:

```python
@pytest.mark.asyncio
async def test_runtime_marks_repo_freshness_mixed_live_and_cached():
    ...
    repos = {repo["path"]: repo for repo in payload["repos"]}
    assert repos["/work/repo-ok"]["freshness"]["state"] == "live"
    assert repos["/work/repo-fail"]["freshness"]["state"] == "cached"
    assert repos["/work/repo-fail"]["freshness"]["reason"] == "poll_error"
```

```python
def test_normalize_passes_through_freshness():
    normalized = normalize_server_payload(...)
    assert "freshness" in normalized
```

- [ ] **Step 2: Run targeted tests and confirm failure**

Run: `uv run pytest tests/dashboard/test_runtime.py -k "repo and freshness" -q`  
Expected: FAIL due missing repo freshness payload.

Run: `uv run pytest tests/dashboard/test_normalize.py -q`  
Expected: FAIL for missing normalized `freshness`.

- [ ] **Step 3: Implement repo freshness + normalization field**

In `runtime.py`:

- Add repo poll health map:

```python
self._repo_last_poll_ok: dict[str, dict[str, bool]] = {}
```

- Record success/failure per repo path during `_poll_git_repos`.
- Attach `repo["freshness"] = ...` while building final repo payload.
- Compute thresholds:
  - `system/gpu = metrics_interval_seconds * 2`
  - `git/clash/repo = status_interval_seconds * 2`

In `normalize.py`:

```python
"freshness": payload.get("freshness", {}),
```

- [ ] **Step 4: Re-run targeted tests**

Run: `uv run pytest tests/dashboard/test_runtime.py -k "freshness" -q`  
Expected: PASS.

Run: `uv run pytest tests/dashboard/test_normalize.py -q`  
Expected: PASS.

- [ ] **Step 5: Commit chunk changes**

Run:

```bash
git add tests/dashboard/test_runtime.py tests/dashboard/test_normalize.py src/server_monitor/dashboard/runtime.py src/server_monitor/dashboard/normalize.py
git commit -m "feat: add repo freshness and normalize freshness payload"
```

## Chunk 2: Frontend Freshness Badge Rendering

### Task 3: Render badges and remove stale header

**Files:**
- Modify: `tests/dashboard/test_static_routes.py`
- Modify: `src/server_monitor/dashboard/static/app.js`
- Modify: `src/server_monitor/dashboard/static/styles.css`

- [ ] **Step 1: Write failing static asset tests**

Add tests in `tests/dashboard/test_static_routes.py` asserting:

- Freshness badge renderer exists in `app.js`.
- Panel render calls reference `update.freshness`.
- Repo row render references `repo.freshness`.
- `stale: ${stale}` string is absent from `app.js`.

Example assertion:

```python
assert "renderFreshnessBadge" in response.text
assert "update.freshness" in response.text
assert "repo.freshness" in response.text
assert "stale: ${stale}" not in response.text
```

- [ ] **Step 2: Run tests to verify failure**

Run: `uv run pytest tests/dashboard/test_static_routes.py -q`  
Expected: FAIL on missing freshness badge code and stale-line removal assertions.

- [ ] **Step 3: Implement minimal UI rendering changes**

In `app.js`:

- Add helper:

```javascript
function renderFreshnessBadge(freshness) {
  const state = freshness && freshness.state === "live" ? "live" : "cached";
  const label = state === "live" ? "LIVE" : "CACHED";
  return `<span class="freshness-badge freshness-${state}">${label}</span>`;
}
```

- Update `renderPanelGroup(...)` to accept optional `summaryBadgeHtml` and render it in `<summary>`.
- Pass badges from `update.freshness.system/gpu/git/clash`.
- In repo rows, render `renderFreshnessBadge(repo.freshness)`.
- Remove:

```javascript
const stale = update.stale ? "yes" : "no";
...
<div class="muted">stale: ${stale}</div>
```

In `styles.css`:

- Add classes:

```css
.freshness-badge { ... }
.freshness-live { ... }
.freshness-cached { ... }
```

- Add summary layout helper class for title + badge alignment.

- [ ] **Step 4: Re-run static tests**

Run: `uv run pytest tests/dashboard/test_static_routes.py -q`  
Expected: PASS.

- [ ] **Step 5: Commit chunk changes**

Run:

```bash
git add tests/dashboard/test_static_routes.py src/server_monitor/dashboard/static/app.js src/server_monitor/dashboard/static/styles.css
git commit -m "feat: render live cached freshness badges in dashboard ui"
```

## Chunk 3: Verification and Handoff

### Task 4: End-to-end verification for freshness slice

**Files:**
- No new files expected (verification only unless regressions found)

- [ ] **Step 1: Run focused regression suite**

Run:

```bash
uv run pytest tests/dashboard/test_runtime.py tests/dashboard/test_normalize.py tests/dashboard/test_static_routes.py -q
```

Expected: PASS.

- [ ] **Step 2: Run full quality checks**

Run:

```bash
uv run pytest -q
uv run ruff check .
```

Expected: PASS with no lint errors.

- [ ] **Step 3: Commit follow-up fixes if verification uncovered issues**

If verification requires code/test adjustments:

```bash
git add <updated files>
git commit -m "fix: address freshness badge verification regressions"
```

- [ ] **Step 4: Capture completion evidence**

Record in PR/summary:

- Runtime payload now includes `freshness` for all panels.
- Repo payload includes per-row `freshness`.
- UI shows `LIVE/CACHED` badges and no longer renders server-level stale line.
- Test commands and final pass status.

