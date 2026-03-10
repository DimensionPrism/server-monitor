"""Settings models and persistent store for agentless dashboard."""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import Literal
import tempfile
import tomllib

import tomli_w


PanelName = Literal["system", "gpu", "git", "clash"]


@dataclass(slots=True)
class ServerSettings:
    """One remote server definition used by SSH polling runtime."""

    server_id: str
    ssh_alias: str
    working_dirs: list[str] = field(default_factory=list)
    enabled_panels: list[PanelName] = field(default_factory=lambda: ["system", "gpu", "git", "clash"])


@dataclass(slots=True)
class DashboardSettings:
    """Top-level dashboard settings persisted in TOML."""

    metrics_interval_seconds: float = 3.0
    status_interval_seconds: float = 12.0
    servers: list[ServerSettings] = field(default_factory=list)


class DashboardSettingsStore:
    """CRUD store for dashboard settings file."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> DashboardSettings:
        if not self.path.exists():
            return DashboardSettings()

        raw = tomllib.loads(self.path.read_text(encoding="utf-8"))
        servers = [
            ServerSettings(
                server_id=item["server_id"],
                ssh_alias=item["ssh_alias"],
                working_dirs=list(item.get("working_dirs", [])),
                enabled_panels=list(item.get("enabled_panels", ["system", "gpu", "git", "clash"])),
            )
            for item in raw.get("servers", [])
        ]
        return DashboardSettings(
            metrics_interval_seconds=float(raw.get("metrics_interval_seconds", 3.0)),
            status_interval_seconds=float(raw.get("status_interval_seconds", 12.0)),
            servers=servers,
        )

    def save(self, settings: DashboardSettings) -> None:
        payload = {
            "metrics_interval_seconds": settings.metrics_interval_seconds,
            "status_interval_seconds": settings.status_interval_seconds,
            "servers": [
                {
                    "server_id": server.server_id,
                    "ssh_alias": server.ssh_alias,
                    "working_dirs": server.working_dirs,
                    "enabled_panels": server.enabled_panels,
                }
                for server in settings.servers
            ],
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_path = tempfile.mkstemp(prefix="servers-", suffix=".toml", dir=str(self.path.parent))
        os.close(fd)
        try:
            with Path(temp_path).open("w", encoding="utf-8") as handle:
                handle.write(tomli_w.dumps(payload))
            Path(temp_path).replace(self.path)
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def create_server(self, server: ServerSettings) -> None:
        settings = self.load()
        if any(existing.server_id == server.server_id for existing in settings.servers):
            raise ValueError(f"server_id '{server.server_id}' already exists")
        settings.servers.append(server)
        self.save(settings)

    def update_server(self, server_id: str, updated: ServerSettings) -> None:
        settings = self.load()
        for index, server in enumerate(settings.servers):
            if server.server_id == server_id:
                settings.servers[index] = updated
                self.save(settings)
                return
        raise KeyError(server_id)

    def delete_server(self, server_id: str) -> None:
        settings = self.load()
        settings.servers = [server for server in settings.servers if server.server_id != server_id]
        self.save(settings)
