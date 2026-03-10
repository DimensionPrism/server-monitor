"""Configuration models for the local dashboard."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib


@dataclass(slots=True)
class ServerConfig:
    """Connection settings for one remote server."""

    server_id: str
    host: str
    user: str
    ssh_port: int = 22
    local_tunnel_port: int = 19000
    agent_port: int = 9000
    repo_paths: list[str] | None = None


@dataclass(slots=True)
class DashboardConfig:
    """Root dashboard configuration."""

    metrics_interval_seconds: float = 3.0
    status_interval_seconds: float = 12.0
    servers: list[ServerConfig] | None = None


def load_dashboard_config(path: str | Path) -> DashboardConfig:
    """Read dashboard config from TOML file."""

    raw = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    servers = [
        ServerConfig(
            server_id=server["server_id"],
            host=server["host"],
            user=server["user"],
            ssh_port=int(server.get("ssh_port", 22)),
            local_tunnel_port=int(server.get("local_tunnel_port", 19000)),
            agent_port=int(server.get("agent_port", 9000)),
            repo_paths=list(server.get("repo_paths", [])),
        )
        for server in raw.get("servers", [])
    ]
    return DashboardConfig(
        metrics_interval_seconds=float(raw.get("metrics_interval_seconds", 3.0)),
        status_interval_seconds=float(raw.get("status_interval_seconds", 12.0)),
        servers=servers,
    )

