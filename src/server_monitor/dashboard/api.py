"""FastAPI routes for local dashboard service."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from server_monitor.dashboard.ws_hub import WebSocketHub


def create_dashboard_app(*, ws_hub: WebSocketHub) -> FastAPI:
    """Create FastAPI app exposing health and websocket routes."""

    app = FastAPI(title="Server Monitor Dashboard")
    static_dir = Path(__file__).with_name("static")
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(static_dir / "index.html")

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
