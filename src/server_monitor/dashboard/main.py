"""Entrypoint for local dashboard server."""

from __future__ import annotations

from datetime import UTC, datetime

from server_monitor.dashboard.api import create_dashboard_app
from server_monitor.dashboard.normalize import normalize_server_payload
from server_monitor.dashboard.ws_hub import WebSocketHub


def build_dashboard_app():
    """Create dashboard app instance."""

    return create_dashboard_app(ws_hub=WebSocketHub())


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
