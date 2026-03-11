"""Pydantic models for snapshots exchanged between services."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class GpuProcess(BaseModel):
    """Single process using a GPU."""

    pid: int = Field(ge=0)
    user: str
    command: str
    gpu_memory_mb: float = Field(ge=0)


class GpuMetrics(BaseModel):
    """GPU utilization summary for a single device."""

    index: int = Field(ge=0)
    name: str
    utilization_gpu: float = Field(ge=0, le=100)
    memory_used_mb: float = Field(ge=0)
    memory_total_mb: float = Field(gt=0)
    temperature_c: float | None = None
    processes: list[GpuProcess] = []


class RepoStatus(BaseModel):
    """Git status summary for one tracked repository."""

    path: str
    branch: str
    dirty: bool
    ahead: int = Field(ge=0)
    behind: int = Field(ge=0)
    staged: int = Field(ge=0)
    unstaged: int = Field(ge=0)
    untracked: int = Field(ge=0)
    last_commit_age_seconds: int = Field(ge=0)


class ClashStatus(BaseModel):
    """Status of clash-for-linux on a remote server."""

    running: bool
    api_reachable: bool
    ui_reachable: bool
    message: str = ""
    ip_location: str = ""
    controller_port: str = ""


class ServerSnapshot(BaseModel):
    """Combined read-only monitoring snapshot for one server."""

    server_id: str
    timestamp: datetime
    cpu_percent: float = Field(ge=0, le=100)
    memory_percent: float = Field(ge=0, le=100)
    disk_percent: float = Field(ge=0, le=100)
    network_rx_kbps: float = Field(ge=0)
    network_tx_kbps: float = Field(ge=0)
    gpus: list[GpuMetrics] = []
    repos: list[RepoStatus] = []
    clash: ClashStatus
    metadata: dict[str, str] = {}
