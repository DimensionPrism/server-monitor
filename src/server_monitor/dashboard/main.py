"""Entrypoint for local dashboard server."""

from __future__ import annotations

from datetime import UTC, datetime
import os
from pathlib import Path

from server_monitor.dashboard.api import create_dashboard_app
from server_monitor.dashboard.clash_tunnel import ClashTunnelManager
from server_monitor.dashboard.metrics_stream_manager import MetricsStreamManager
from server_monitor.dashboard.normalize import normalize_server_payload
from server_monitor.dashboard.persistent_session import PersistentBatchTransport
from server_monitor.dashboard.runtime import DashboardRuntime, SshCommandExecutor
from server_monitor.dashboard.settings import DashboardSettings, DashboardSettingsStore, ServerSettings
from server_monitor.dashboard.ws_hub import WebSocketHub


def build_dashboard_app():
    """Create dashboard app instance."""

    hub = WebSocketHub()
    settings_store = _build_settings_store()
    runtime = _build_runtime(hub, settings_store)
    clash_tunnel_manager = ClashTunnelManager()
    return create_dashboard_app(
        ws_hub=hub,
        runtime=runtime,
        settings_store=settings_store,
        clash_tunnel_manager=clash_tunnel_manager,
    )


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


def _build_settings_store() -> DashboardSettingsStore:
    config_path = Path(os.getenv("SERVER_MONITOR_SETTINGS_PATH", "config/servers.toml"))
    store = DashboardSettingsStore(config_path)
    if not config_path.exists():
        fallback_alias = os.getenv("SERVER_MONITOR_SSH_ALIAS")
        if fallback_alias:
            store.save(
                DashboardSettings(
                    servers=[
                        ServerSettings(
                            server_id=os.getenv("SERVER_MONITOR_FALLBACK_SERVER_ID", "server-a"),
                            ssh_alias=fallback_alias,
                        )
                    ]
                )
            )
    return store


def _build_runtime(hub: WebSocketHub, settings_store: DashboardSettingsStore) -> DashboardRuntime:
    return DashboardRuntime(
        hub=hub,
        settings_store=settings_store,
        executor=SshCommandExecutor(),
        batch_transport=PersistentBatchTransport(),
        metrics_stream_manager=MetricsStreamManager(),
        stale_after_seconds=15.0,
    )
