"""Background polling runtime for dashboard live updates."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx

from server_monitor.dashboard.normalize import normalize_server_payload
from server_monitor.dashboard.ws_hub import WebSocketHub


@dataclass(slots=True)
class PollSource:
    """One upstream agent exposed through local network/tunnel."""

    server_id: str
    base_url: str


class DashboardRuntime:
    """Poll upstream agents and broadcast normalized websocket updates."""

    def __init__(
        self,
        *,
        hub: WebSocketHub,
        sources: list[PollSource],
        interval_seconds: float,
        stale_after_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.hub = hub
        self.sources = sources
        self.interval_seconds = interval_seconds
        self.stale_after_seconds = stale_after_seconds
        self.transport = transport
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run_loop(), name="dashboard-runtime-loop")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stop_event.set()
        self._task.cancel()
        with suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def poll_once(self) -> None:
        async with httpx.AsyncClient(timeout=2.0, transport=self.transport) as client:
            for source in self.sources:
                await self._poll_source(client, source)

    async def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            await self.poll_once()
            await asyncio.sleep(self.interval_seconds)

    async def _poll_source(self, client: httpx.AsyncClient, source: PollSource) -> None:
        try:
            snapshot_resp = await client.get(f"{source.base_url}/snapshot")
            repos_resp = await client.get(f"{source.base_url}/repos")
            clash_resp = await client.get(f"{source.base_url}/clash")
            snapshot_resp.raise_for_status()
            repos_resp.raise_for_status()
            clash_resp.raise_for_status()
        except Exception:
            return

        snapshot = snapshot_resp.json()
        repos = repos_resp.json()
        clash = clash_resp.json()
        payload = {
            "timestamp": snapshot.get("timestamp", datetime.now(UTC).isoformat()),
            "snapshot": snapshot,
            "repos": repos,
            "clash": clash,
        }
        normalized = normalize_server_payload(
            server_id=source.server_id,
            payload=payload,
            now=datetime.now(UTC),
            stale_after_seconds=self.stale_after_seconds,
        )
        await self.hub.broadcast(normalized)

