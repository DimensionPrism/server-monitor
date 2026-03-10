"""Configuration model and loader for server agent."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import tomllib


@dataclass(slots=True)
class AgentConfig:
    """Runtime options for a server agent instance."""

    server_id: str
    host: str = "127.0.0.1"
    port: int = 9000
    repo_paths: list[str] = field(default_factory=list)
    metrics_interval_seconds: float = 3.0
    status_interval_seconds: float = 12.0
    system_cmd: list[str] = field(default_factory=list)
    gpu_cmd: list[str] = field(default_factory=list)
    git_status_cmd: list[str] = field(default_factory=list)
    clash_status_cmd: list[str] = field(default_factory=list)


def _default_system_cmd() -> list[str]:
    script = (
        "CPU=$(top -bn1 | awk '/Cpu\\(s\\)/ {print 100-$8; exit}'); "
        "MEM=$(free | awk '/Mem:/ {printf \"%.2f\", ($3/$2)*100}'); "
        "DISK=$(df -P / | awk 'NR==2 {gsub(/%/,\"\",$5); print $5}'); "
        "echo \"CPU: ${CPU:-0}\"; "
        "echo \"MEM: ${MEM:-0}\"; "
        "echo \"DISK: ${DISK:-0}\"; "
        "echo \"RX_KBPS: 0\"; "
        "echo \"TX_KBPS: 0\""
    )
    return ["bash", "-lc", script]


def _default_gpu_cmd() -> list[str]:
    return [
        "bash",
        "-lc",
        "nvidia-smi --query-gpu=index,name,utilization.gpu,memory.used,memory.total,temperature.gpu --format=csv,noheader,nounits",
    ]


def _default_git_status_cmd() -> list[str]:
    return ["git", "-C", "{repo}", "status", "--porcelain", "--branch"]


def _default_clash_status_cmd() -> list[str]:
    script = (
        "if pgrep -f clash >/dev/null; then echo running=true; else echo running=false; fi; "
        "echo api_reachable=false; "
        "echo ui_reachable=false; "
        "echo message=ok"
    )
    return ["bash", "-lc", script]


def load_agent_config(path: str | Path) -> AgentConfig:
    """Load agent configuration from TOML."""

    raw = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    return AgentConfig(
        server_id=raw["server_id"],
        host=raw.get("host", "127.0.0.1"),
        port=int(raw.get("port", 9000)),
        repo_paths=list(raw.get("repo_paths", [])),
        metrics_interval_seconds=float(raw.get("metrics_interval_seconds", 3.0)),
        status_interval_seconds=float(raw.get("status_interval_seconds", 12.0)),
        system_cmd=list(raw.get("system_cmd", _default_system_cmd())),
        gpu_cmd=list(raw.get("gpu_cmd", _default_gpu_cmd())),
        git_status_cmd=list(raw.get("git_status_cmd", _default_git_status_cmd())),
        clash_status_cmd=list(raw.get("clash_status_cmd", _default_clash_status_cmd())),
    )
