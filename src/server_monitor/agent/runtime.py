"""Background runtime loop for agent collectors."""

from __future__ import annotations

import asyncio
from contextlib import suppress


class AgentRuntime:
    """Run metrics and status collectors on independent intervals."""

    def __init__(
        self,
        *,
        metrics_collector,
        repo_clash_collector,
        metrics_interval_seconds: float,
        status_interval_seconds: float,
    ) -> None:
        self.metrics_collector = metrics_collector
        self.repo_clash_collector = repo_clash_collector
        self.metrics_interval_seconds = metrics_interval_seconds
        self.status_interval_seconds = status_interval_seconds
        self._tasks: list[asyncio.Task] = []
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        if self._tasks:
            return
        self._stop_event.clear()
        self._tasks = [
            asyncio.create_task(self._metrics_loop(), name="agent-metrics-loop"),
            asyncio.create_task(self._status_loop(), name="agent-status-loop"),
        ]

    async def stop(self) -> None:
        if not self._tasks:
            return
        self._stop_event.set()
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            with suppress(asyncio.CancelledError):
                await task
        self._tasks = []

    async def _metrics_loop(self) -> None:
        while not self._stop_event.is_set():
            await self.metrics_collector.collect_once()
            await asyncio.sleep(self.metrics_interval_seconds)

    async def _status_loop(self) -> None:
        while not self._stop_event.is_set():
            await self.repo_clash_collector.collect_once()
            await asyncio.sleep(self.status_interval_seconds)

