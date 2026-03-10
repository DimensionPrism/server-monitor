"""Entrypoint for local dashboard server."""

from __future__ import annotations

from server_monitor.dashboard.api import create_dashboard_app
from server_monitor.dashboard.ws_hub import WebSocketHub


def build_dashboard_app():
    """Create dashboard app instance."""

    return create_dashboard_app(ws_hub=WebSocketHub())

