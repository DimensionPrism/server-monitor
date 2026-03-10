"""FastAPI routes exposed by the server agent."""

from __future__ import annotations

from fastapi import FastAPI

from server_monitor.agent.snapshot_store import SnapshotStore


def create_app(store: SnapshotStore) -> FastAPI:
    """Build the read-only monitoring API."""

    app = FastAPI(title="Server Monitor Agent")

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

