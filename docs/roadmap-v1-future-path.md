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

## Current UX Status

- Landed: summary-first monitor cards tuned for 1-4 server daily scanning.
- Landed: collapsed cards show metrics only; detail panels remain opt-in.
- Landed: GPU card summaries now show active/total devices plus peak utilization for multi-GPU hosts.
- Landed: premium monitor styling adds stronger semantic color, richer surfaces, and motion without changing the summary-first information model.
- Landed: GPU heat cues stay local to GPU contexts instead of escalating the full server card.
- Landed: Settings now uses a split workspace with overview rail, grouped editor cards, and a sticky save/delete footer.
- Landed: the `Add Server` form opens by default for first-run setup, then collapses behind an `Add Server` button once saved servers exist.
- Landed: per-card command health strip shows latency-first healthy state and retry/cooldown/failure summaries for enabled panels.

## v1.2 Status

- Landed: policy-driven retry, bounded backoff, short cooldowns, and recent command health journaling in the poller runtime.
- Landed: redaction-safe diagnostics bundle backend at `GET /api/diagnostics`.
- Landed: command latency/error-state telemetry in the monitor UI via the per-card command health strip.
- Landed: lightweight transition-only failure notifications (desktop + optional webhook) from live command health updates.
- Landed: a user-facing diagnostics export action that packages the existing diagnostics bundle for sharing.

## Short-Term TODO (1-3 weeks)

1. Multi-user mode with auth and role-based safe controls (viewer/operator/admin).
2. Historical time-series storage and charts (CPU/GPU/Git drift over time).

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
