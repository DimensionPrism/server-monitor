from fastapi.testclient import TestClient


class _FakeRuntime:
    def __init__(self):
        self.started = False
        self.stopped = False

    async def start(self):
        self.started = True

    async def stop(self):
        self.stopped = True


def test_dashboard_app_starts_and_stops_runtime():
    from server_monitor.dashboard.api import create_dashboard_app
    from server_monitor.dashboard.ws_hub import WebSocketHub

    runtime = _FakeRuntime()
    app = create_dashboard_app(ws_hub=WebSocketHub(), runtime=runtime)

    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200

    assert runtime.started is True
    assert runtime.stopped is True
