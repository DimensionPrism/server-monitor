# v1.1 Freshness Badges Design

## Summary

Implement explicit `LIVE` vs `CACHED` freshness badges for:

- System panel
- GPU panel
- Git panel
- Clash panel
- Each Git repo row

This replaces the current server-level `stale: yes/no` header display.

## Scope

### In Scope

- Backend-owned freshness calculation in dashboard runtime
- Freshness metadata in websocket payloads
- UI rendering for panel-level and repo-level badges
- Hybrid freshness policy:
  - `CACHED` when latest poll failed, or
  - `CACHED` when data age exceeds threshold
- Threshold model:
  - System/GPU: `metrics_interval_seconds * 2`
  - Git/Clash/Repo: `status_interval_seconds * 2`

### Out of Scope

- Real Clash reachability checks (`api_reachable`, `ui_reachable`)
- Clash UI tunnel flow
- Alerting or retry policy changes

## Architecture

Use a backend-owned freshness model in `DashboardRuntime`.

Runtime computes freshness for each panel and each repo row, then sends explicit freshness fields in websocket updates. Frontend only renders badges from this data.

## Payload Contract

Add top-level `freshness` object in each normalized server update:

```json
{
  "freshness": {
    "system": {
      "state": "live|cached",
      "reason": "poll_error|age_expired|no_data",
      "last_updated_at": "ISO8601|null",
      "age_seconds": 0,
      "threshold_seconds": 20
    },
    "gpu": {},
    "git": {},
    "clash": {}
  }
}
```

Add `freshness` object per repo:

```json
{
  "path": "/work/repo-a",
  "freshness": {
    "state": "live|cached",
    "reason": "poll_error|age_expired|no_data",
    "last_updated_at": "ISO8601|null",
    "age_seconds": 0,
    "threshold_seconds": 20
  }
}
```

The legacy `stale` field can remain in payload for compatibility, but UI must stop rendering it.

## Runtime Design

### New Runtime State

Add server-level poll status maps:

- `_system_last_poll_ok: dict[str, bool]`
- `_gpu_last_poll_ok: dict[str, bool]`
- `_git_last_poll_ok: dict[str, bool]`
- `_clash_last_poll_ok: dict[str, bool]`

Add per-repo poll status:

- `_repo_last_poll_ok: dict[str, dict[str, bool]]`

### Poll Result Recording

- System/GPU:
  - Success: update cache, set `last_updated_at`, mark last poll ok.
  - Failure: keep cache, mark last poll failed.
- Git:
  - Per repo poll success/failure tracked in `_repo_last_poll_ok`.
  - Git panel marked ok only when all configured repos succeed in the cycle.
  - Existing cache fallback behavior remains unchanged.
- Clash:
  - Success: parse/update cache, set `last_updated_at`, mark last poll ok.
  - Failure: keep cache, mark last poll failed.

### Freshness Computation

Compute freshness right before normalization/broadcast:

- Panel freshness:
  - Inputs: `last_updated_at`, `last_poll_ok`, current time, threshold
- Repo freshness:
  - Inputs: `repo.last_updated_at`, repo poll status, current time, threshold

### Reason Priority

When computing `state=cached`, apply reason precedence:

1. `poll_error` if latest poll failed
2. `age_expired` if age exceeds threshold
3. `no_data` if there has not been a successful timestamp

## UI Design

Update `src/server_monitor/dashboard/static/app.js`:

- Remove card header `stale: yes/no` display.
- Add shared renderer `renderFreshnessBadge(freshness)`:
  - `LIVE` for `state=live`
  - `CACHED` for `state=cached`
- Render panel badges in System/GPU/Git/Clash section summaries.
- Render repo badge per repo row near existing repo badges/path.
- Keep current "Last update" text line.
- Defensive fallback: if freshness missing, render `CACHED`.

Update `src/server_monitor/dashboard/static/styles.css`:

- Add `.freshness-badge`, `.freshness-live`, `.freshness-cached`
- Align summary-level badge placement for `details > summary`
- Ensure repo badge wraps cleanly on small screens

## Error Handling

- Transient command/parse failures do not clear cached values.
- Badges expose degraded freshness immediately via `CACHED`.
- Missing timestamps resolve to `CACHED` with `reason=no_data`.

## Testing Plan

### Runtime Tests (`tests/dashboard/test_runtime.py`)

- Panel freshness is `LIVE` after successful poll.
- Panel freshness is `CACHED` with `poll_error` after failed poll.
- Panel freshness is `CACHED` with `age_expired` when beyond threshold.
- Repo freshness supports mixed outcomes in one cycle.
- Repo/panel freshness returns `no_data` before first success.

### Static Asset Tests (`tests/dashboard/test_static_routes.py`)

- `app.js` includes freshness badge rendering hooks.
- Server-level stale header string is removed.
- Repo rendering includes freshness badge hook.

## Acceptance Criteria

- Each enabled panel (System/GPU/Git/Clash) shows explicit `LIVE` or `CACHED`.
- Each repo row shows explicit `LIVE` or `CACHED`.
- Freshness follows hybrid policy with per-panel interval-derived thresholds.
- Existing cache fallback behavior remains stable.
- Old server-level stale header is no longer rendered.
