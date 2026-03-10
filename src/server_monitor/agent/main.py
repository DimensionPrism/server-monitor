"""Entrypoint for running the server agent."""

from __future__ import annotations

from server_monitor.agent.api import create_app
from server_monitor.agent.config import load_agent_config
from server_monitor.agent.snapshot_store import SnapshotStore


def build_app_from_config(config_path: str):
    """Create an app instance based on config file."""

    config = load_agent_config(config_path)
    store = SnapshotStore(server_id=config.server_id)
    return create_app(store)

