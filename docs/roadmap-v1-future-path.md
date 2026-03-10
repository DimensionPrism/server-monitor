# Server Monitor Future Path (Post-v1)

## Short-Term TODO (1-3 weeks)

1. Add explicit freshness badges (`LIVE` vs `CACHED`) on System/GPU/Git/Clash sections and per repo row.
2. Implement real Clash reachability checks instead of placeholder booleans (`api_reachable`, `ui_reachable`).
3. Add one-click Clash UI tunnel open flow from dashboard (agentless SSH local forward).
4. Add command latency and error-rate telemetry in UI (per server command health strip).
5. Improve retry and timeout strategy per command type (GPU/System/Git/Clash) with bounded backoff.
6. Add lightweight notification hooks for failures (desktop toast + optional webhook).
7. Add exportable diagnostics bundle (current settings + last N poll errors + timings).

## Long-Term Roadmap (1-3 months)

1. Multi-user mode with auth and role-based safe controls (viewer/operator/admin).
2. Historical time-series storage and charts (CPU/GPU/Git drift over time).
3. Policy engine for safe ops (branch allowlists, protected repos, operation windows).
4. Remote command abstraction layer to support non-SSH backends later.
5. Plugin panel framework for custom per-server checks and domain-specific monitors.
6. Incident workflow integration (alert routing, acknowledgement, runbook links).
7. Optional hosted control plane for managing many servers/workspaces centrally.

## Release Sequencing

1. `v1.1`: Freshness UX + Clash real checks + tunnel open.
2. `v1.2`: Reliability and diagnostics (timeouts/retries/health/notifications).
3. `v1.3`: Historical data + policy controls.
4. `v2.0`: Multi-user and plugin-oriented architecture.
