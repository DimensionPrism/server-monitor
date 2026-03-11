# Server Monitor Future Path (Post-v1)

## v1.1 Status

`v1.1` is implemented in the current codebase.

- Landed: freshness badges (`LIVE`/`CACHED`) for dashboard panels and repo rows.
- Landed: real secret-aware Clash API/UI reachability checks with configurable probe URLs.
- Landed: non-blocking status poll path so SSH status stalls no longer block refresh cycles or overwrite last-known Clash state on transient secret-command failures.
- Landed: one-click Clash UI tunnel-open flow from the dashboard (agentless SSH local forward).
- Landed: Clash UI login-assist flow (secret handoff + auto-login setup URL + copy-secret action).
- Landed: Clash secret probing fallback path for non-interactive SSH shells (`clashsecret`/`clashctl secret`/`runtime.yaml`).
- Landed: Clash probe success accepts `2xx` and redirect `3xx` responses.

## Short-Term TODO (1-3 weeks)

1. Add command latency and error-rate telemetry in UI (per server command health strip).
2. Improve retry and timeout strategy per command type (GPU/System/Git/Clash) with bounded backoff.
3. Add lightweight notification hooks for failures (desktop toast + optional webhook).
4. Add exportable diagnostics bundle (current settings + last N poll errors + timings).

## Long-Term Roadmap (1-3 months)

1. Multi-user mode with auth and role-based safe controls (viewer/operator/admin).
2. Historical time-series storage and charts (CPU/GPU/Git drift over time).
3. Policy engine for safe ops (branch allowlists, protected repos, operation windows).
4. Remote command abstraction layer to support non-SSH backends later.
5. Plugin panel framework for custom per-server checks and domain-specific monitors.
6. Incident workflow integration (alert routing, acknowledgement, runbook links).
7. Optional hosted control plane for managing many servers/workspaces centrally.

## Release Sequencing

1. `v1.1`: Freshness UX + secret-aware Clash reachability + one-click tunnel open + Clash login assist.
2. `v1.2`: Reliability and diagnostics (timeouts/retries/health/notifications).
3. `v1.3`: Historical data + policy controls.
4. `v2.0`: Multi-user and plugin-oriented architecture.
