"""WebSocket broadcast hub."""

from __future__ import annotations


class WebSocketHub:
    """Manage live dashboard websocket connections."""

    def __init__(self) -> None:
        self._connections: set = set()

    @property
    def connection_count(self) -> int:
        return len(self._connections)

    async def connect(self, websocket) -> None:
        self._connections.add(websocket)

    async def disconnect(self, websocket) -> None:
        self._connections.discard(websocket)

    async def broadcast(self, payload: dict) -> None:
        stale_connections = []
        for websocket in self._connections:
            try:
                await websocket.send_json(payload)
            except Exception:
                stale_connections.append(websocket)

        for websocket in stale_connections:
            self._connections.discard(websocket)

