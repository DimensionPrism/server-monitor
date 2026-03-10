"""FastAPI routes for local dashboard service."""

from __future__ import annotations

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from server_monitor.dashboard.ws_hub import WebSocketHub


def create_dashboard_app(*, ws_hub: WebSocketHub) -> FastAPI:
    """Create FastAPI app exposing health and websocket routes."""

    app = FastAPI(title="Server Monitor Dashboard")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.websocket("/ws")
    async def websocket_stream(websocket: WebSocket) -> None:
        await websocket.accept()
        await ws_hub.connect(websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            await ws_hub.disconnect(websocket)

    return app

