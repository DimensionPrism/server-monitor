"""Collector for system and GPU metrics."""

from __future__ import annotations

from datetime import UTC, datetime

from server_monitor.agent.parsers.gpu import parse_gpu_snapshot
from server_monitor.agent.parsers.system import parse_system_snapshot
from server_monitor.agent.snapshot_store import SnapshotStore


class MetricsCollector:
    """Collect fast-updating resource metrics."""

    def __init__(
        self,
        *,
        runner,
        store: SnapshotStore,
        system_cmd: list[str],
        gpu_cmd: list[str],
    ) -> None:
        self.runner = runner
        self.store = store
        self.system_cmd = system_cmd
        self.gpu_cmd = gpu_cmd

    async def collect_once(self, *, now: datetime | None = None) -> None:
        timestamp = now or datetime.now(UTC)
        system_result = await self.runner.run(self.system_cmd)
        gpu_result = await self.runner.run(self.gpu_cmd)

        if system_result.exit_code != 0 or system_result.error:
            self.store.record_metrics_error(system_result.error or system_result.stderr or "system command failed")
            return
        if gpu_result.exit_code != 0 or gpu_result.error:
            self.store.record_metrics_error(gpu_result.error or gpu_result.stderr or "gpu command failed")
            return

        system_metrics = parse_system_snapshot(system_result.stdout)
        gpu_metrics = parse_gpu_snapshot(gpu_result.stdout)
        self.store.update_metrics(
            {
                **system_metrics,
                "gpus": gpu_metrics,
            },
            timestamp=timestamp,
        )

