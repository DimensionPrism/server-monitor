from fastapi.testclient import TestClient


def test_health_endpoint():
    from server_monitor.agent.api import create_app
    from server_monitor.agent.snapshot_store import SnapshotStore

    app = create_app(SnapshotStore(server_id="server-a"))
    client = TestClient(app)

    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_snapshot_endpoint_returns_snapshot_shape():
    from server_monitor.agent.api import create_app
    from server_monitor.agent.snapshot_store import SnapshotStore

    app = create_app(SnapshotStore(server_id="server-a"))
    client = TestClient(app)

    response = client.get("/snapshot")
    body = response.json()

    assert response.status_code == 200
    assert body["server_id"] == "server-a"
    assert "cpu_percent" in body
    assert "clash" in body
