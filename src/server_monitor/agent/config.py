"""Configuration model and loader for server agent."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib


@dataclass(slots=True)
class AgentConfig:
    """Runtime options for a server agent instance."""

    server_id: str
    host: str = "127.0.0.1"
    port: int = 9000
    repo_paths: list[str] | None = None


def load_agent_config(path: str | Path) -> AgentConfig:
    """Load agent configuration from TOML."""

    raw = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    return AgentConfig(
        server_id=raw["server_id"],
        host=raw.get("host", "127.0.0.1"),
        port=int(raw.get("port", 9000)),
        repo_paths=list(raw.get("repo_paths", [])),
    )

