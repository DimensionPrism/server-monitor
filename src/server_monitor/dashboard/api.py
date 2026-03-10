"""FastAPI routes for local dashboard service."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from server_monitor.dashboard.settings import DashboardSettings, DashboardSettingsStore, ServerSettings
from server_monitor.dashboard.ws_hub import WebSocketHub


def _build_lifespan(runtime):
    @asynccontextmanager
    async def _lifespan(_app: FastAPI):
        if runtime is not None:
            await runtime.start()
        try:
            yield
        finally:
            if runtime is not None:
                await runtime.stop()

    return _lifespan


class ServerPayload(BaseModel):
    server_id: str
    ssh_alias: str
    working_dirs: list[str] = []
    enabled_panels: list[str] = ["system", "gpu", "git", "clash"]
    clash_api_probe_url: str = "http://127.0.0.1:9090/version"
    clash_ui_probe_url: str = "http://127.0.0.1:9090/ui"


class PathPayload(BaseModel):
    path: str


class PanelsPayload(BaseModel):
    enabled_panels: list[str]


class GitOpPayload(BaseModel):
    repo_path: str
    operation: str
    branch: str | None = None


SAFE_GIT_OPERATIONS = {"refresh", "fetch", "pull", "checkout"}


def _serialize_settings(settings: DashboardSettings) -> dict:
    return {
        "metrics_interval_seconds": settings.metrics_interval_seconds,
        "status_interval_seconds": settings.status_interval_seconds,
        "servers": [
            {
                "server_id": server.server_id,
                "ssh_alias": server.ssh_alias,
                "working_dirs": server.working_dirs,
                "enabled_panels": server.enabled_panels,
                "clash_api_probe_url": server.clash_api_probe_url,
                "clash_ui_probe_url": server.clash_ui_probe_url,
            }
            for server in settings.servers
        ],
    }


def _require_store(settings_store: DashboardSettingsStore | None) -> DashboardSettingsStore:
    if settings_store is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="settings store unavailable")
    return settings_store


def _find_server(settings: DashboardSettings, server_id: str) -> ServerSettings:
    for server in settings.servers:
        if server.server_id == server_id:
            return server
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown server '{server_id}'")


def _require_git_runtime(runtime):
    if runtime is None or not hasattr(runtime, "run_git_operation"):
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="git operations unavailable")
    return runtime


def create_dashboard_app(*, ws_hub: WebSocketHub, runtime=None, settings_store: DashboardSettingsStore | None = None) -> FastAPI:
    """Create FastAPI app exposing health and websocket routes."""

    app = FastAPI(title="Server Monitor Dashboard", lifespan=_build_lifespan(runtime))
    static_dir = Path(__file__).with_name("static")
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/settings")
    def get_settings() -> dict:
        store = _require_store(settings_store)
        return _serialize_settings(store.load())

    @app.post("/api/servers", status_code=status.HTTP_201_CREATED)
    def create_server(payload: ServerPayload) -> dict:
        store = _require_store(settings_store)
        try:
            store.create_server(
                ServerSettings(
                    server_id=payload.server_id,
                    ssh_alias=payload.ssh_alias,
                    working_dirs=payload.working_dirs,
                    enabled_panels=payload.enabled_panels,
                    clash_api_probe_url=payload.clash_api_probe_url,
                    clash_ui_probe_url=payload.clash_ui_probe_url,
                )
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        return _serialize_settings(store.load())

    @app.put("/api/servers/{server_id}")
    def update_server(server_id: str, payload: ServerPayload) -> dict:
        store = _require_store(settings_store)
        if payload.server_id != server_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="server_id mismatch")
        try:
            store.update_server(
                server_id,
                ServerSettings(
                    server_id=payload.server_id,
                    ssh_alias=payload.ssh_alias,
                    working_dirs=payload.working_dirs,
                    enabled_panels=payload.enabled_panels,
                    clash_api_probe_url=payload.clash_api_probe_url,
                    clash_ui_probe_url=payload.clash_ui_probe_url,
                ),
            )
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown server '{server_id}'") from exc
        return _serialize_settings(store.load())

    @app.delete("/api/servers/{server_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_server(server_id: str) -> None:
        store = _require_store(settings_store)
        store.delete_server(server_id)

    @app.post("/api/servers/{server_id}/working-dirs")
    def add_working_dir(server_id: str, payload: PathPayload) -> dict:
        store = _require_store(settings_store)
        settings = store.load()
        server = _find_server(settings, server_id)
        if payload.path not in server.working_dirs:
            server.working_dirs.append(payload.path)
            store.update_server(server_id, server)
        return _serialize_settings(store.load())

    @app.delete("/api/servers/{server_id}/working-dirs")
    def remove_working_dir(server_id: str, payload: PathPayload) -> dict:
        store = _require_store(settings_store)
        settings = store.load()
        server = _find_server(settings, server_id)
        server.working_dirs = [item for item in server.working_dirs if item != payload.path]
        store.update_server(server_id, server)
        return _serialize_settings(store.load())

    @app.put("/api/servers/{server_id}/panels")
    def update_panels(server_id: str, payload: PanelsPayload) -> dict:
        store = _require_store(settings_store)
        settings = store.load()
        server = _find_server(settings, server_id)
        server.enabled_panels = payload.enabled_panels
        store.update_server(server_id, server)
        return _serialize_settings(store.load())

    @app.post("/api/servers/{server_id}/git/ops")
    async def run_git_op(server_id: str, payload: GitOpPayload) -> dict:
        if payload.operation not in SAFE_GIT_OPERATIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"unsupported operation '{payload.operation}'",
            )

        git_runtime = _require_git_runtime(runtime)
        try:
            return await git_runtime.run_git_operation(
                server_id=server_id,
                repo_path=payload.repo_path,
                operation=payload.operation,
                branch=payload.branch,
            )
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

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
