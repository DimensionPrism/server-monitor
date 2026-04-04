"""SSH tunnel lifecycle management."""

from __future__ import annotations


class SSH_TunnelManager:
    """Track connection state and reconnect backoff."""

    def __init__(self, *, connect, base_backoff_seconds: float = 1.0) -> None:
        self._connect = connect
        self.base_backoff_seconds = base_backoff_seconds
        self.current_backoff_seconds = 0.0
        self.state = "down"

    async def ensure_connected(self) -> None:
        connected = await self._connect()
        if connected:
            self.state = "connected"
            self.current_backoff_seconds = 0.0
            return

        self.state = "reconnecting"
        self.current_backoff_seconds = max(
            self.base_backoff_seconds,
            self.current_backoff_seconds * 2
            if self.current_backoff_seconds
            else self.base_backoff_seconds,
        )
