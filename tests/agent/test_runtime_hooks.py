from fastapi.testclient import TestClient


class _FakeRuntime:
    def __init__(self):
        self.started = False
        self.stopped = False

    async def start(self):
        self.started = True

    async def stop(self):
        self.stopped = True


def test_agent_app_starts_and_stops_runtime():
    from server_monitor.agent.api import create_app
    from server_monitor.agent.snapshot_store import SnapshotStore

    runtime = _FakeRuntime()
    app = create_app(SnapshotStore(server_id="server-a"), runtime=runtime)

    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200

    assert runtime.started is True
    assert runtime.stopped is True
