"""Entrypoint for local dashboard server."""

from __future__ import annotations

from datetime import UTC, datetime
import os
from pathlib import Path

from server_monitor.dashboard.api import create_dashboard_app
from server_monitor.dashboard.config import load_dashboard_config
from server_monitor.dashboard.normalize import normalize_server_payload
from server_monitor.dashboard.runtime import DashboardRuntime, PollSource
from server_monitor.dashboard.ws_hub import WebSocketHub


def build_dashboard_app():
    """Create dashboard app instance."""

    hub = WebSocketHub()
    runtime = _build_runtime(hub)
    return create_dashboard_app(ws_hub=hub, runtime=runtime)


async def emit_dashboard_update(
    *,
    hub: WebSocketHub,
    server_id: str,
    payload: dict,
    now: datetime | None = None,
    stale_after_seconds: float = 10.0,
) -> None:
    """Normalize one server payload and broadcast it to active clients."""

    current_time = now or datetime.now(UTC)
    normalized = normalize_server_payload(
        server_id=server_id,
        payload=payload,
        now=current_time,
        stale_after_seconds=stale_after_seconds,
    )
    await hub.broadcast(normalized)


def _build_runtime(hub: WebSocketHub) -> DashboardRuntime:
    config_path = Path(os.getenv("SERVER_MONITOR_DASHBOARD_CONFIG", "config/local-dashboard.toml"))
    if config_path.exists():
        config = load_dashboard_config(config_path)
        sources = [
            PollSource(
                server_id=server.server_id,
                base_url=f"http://127.0.0.1:{server.local_tunnel_port}",
            )
            for server in (config.servers or [])
        ]
        return DashboardRuntime(
            hub=hub,
            sources=sources,
            interval_seconds=config.metrics_interval_seconds,
            stale_after_seconds=max(config.status_interval_seconds, config.metrics_interval_seconds * 2),
        )

    # Fallback for local smoke runs when no dashboard config exists yet.
    default_source = PollSource(
        server_id=os.getenv("SERVER_MONITOR_FALLBACK_SERVER_ID", "server-a"),
        base_url=os.getenv("SERVER_MONITOR_AGENT_BASE_URL", "http://127.0.0.1:9000"),
    )
    return DashboardRuntime(
        hub=hub,
        sources=[default_source],
        interval_seconds=3.0,
        stale_after_seconds=10.0,
    )
