"""FastAPI routes exposed by the server agent."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from server_monitor.agent.snapshot_store import SnapshotStore


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


def create_app(store: SnapshotStore, runtime=None) -> FastAPI:
    """Build the read-only monitoring API."""

    app = FastAPI(title="Server Monitor Agent", lifespan=_build_lifespan(runtime))

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/snapshot")
    def snapshot() -> dict:
        return store.snapshot.model_dump(mode="json")

    @app.get("/repos")
    def repos() -> list[dict]:
        return [repo.model_dump(mode="json") for repo in store.snapshot.repos]

    @app.get("/clash")
    def clash() -> dict:
        return store.snapshot.clash.model_dump(mode="json")

    return app
