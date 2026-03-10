"""Polling utilities for dashboard data refresh."""

from __future__ import annotations

from datetime import UTC, datetime


class AgentPoller:
    """Poll one agent endpoint group and emit a merged update."""

    def __init__(self, *, server_id: str, fetch_json, on_update) -> None:
        self.server_id = server_id
        self.fetch_json = fetch_json
        self.on_update = on_update

    async def poll_once(self) -> None:
        snapshot = await self.fetch_json("/snapshot")
        repos = await self.fetch_json("/repos")
        clash = await self.fetch_json("/clash")
        update = {
            "server_id": self.server_id,
            "timestamp": datetime.now(UTC).isoformat(),
            "snapshot": snapshot,
            "repos": repos,
            "clash": clash,
        }
        await self.on_update(update)

