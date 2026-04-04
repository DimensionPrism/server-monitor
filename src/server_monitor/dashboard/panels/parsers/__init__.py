"""Output parsers for SSH command results."""

from __future__ import annotations

from server_monitor.dashboard.panels.parsers.clash import parse_clash_status
from server_monitor.dashboard.panels.parsers.git_status import parse_repo_status
from server_monitor.dashboard.panels.parsers.gpu import parse_gpu_snapshot
from server_monitor.dashboard.panels.parsers.system import parse_system_snapshot

__all__ = [
    "parse_clash_status",
    "parse_repo_status",
    "parse_gpu_snapshot",
    "parse_system_snapshot",
]
