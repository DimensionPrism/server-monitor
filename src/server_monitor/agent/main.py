"""Entrypoint for running the server agent."""

from __future__ import annotations

import os

from server_monitor.agent.api import create_app
from server_monitor.agent.collectors.metrics_collector import MetricsCollector
from server_monitor.agent.collectors.repo_clash_collector import RepoClashCollector
from server_monitor.agent.command_runner import CommandRunner
from server_monitor.agent.config import load_agent_config
from server_monitor.agent.runtime import AgentRuntime
from server_monitor.agent.snapshot_store import SnapshotStore


def build_app_from_config(config_path: str):
    """Create an app instance based on config file."""

    config = load_agent_config(config_path)
    store = SnapshotStore(server_id=config.server_id)
    runner = CommandRunner(timeout_seconds=5.0)
    metrics_collector = MetricsCollector(
        runner=runner,
        store=store,
        system_cmd=config.system_cmd,
        gpu_cmd=config.gpu_cmd,
    )
    repo_clash_collector = RepoClashCollector(
        runner=runner,
        store=store,
        repo_paths=config.repo_paths,
        git_status_cmd=config.git_status_cmd,
        clash_status_cmd=config.clash_status_cmd,
    )
    runtime = AgentRuntime(
        metrics_collector=metrics_collector,
        repo_clash_collector=repo_clash_collector,
        metrics_interval_seconds=config.metrics_interval_seconds,
        status_interval_seconds=config.status_interval_seconds,
    )
    return create_app(store, runtime=runtime)


def build_app():
    """Create app from env-selected config for uvicorn --factory usage."""

    config_path = os.getenv("SERVER_MONITOR_AGENT_CONFIG", "config/agent.example.toml")
    return build_app_from_config(config_path)
