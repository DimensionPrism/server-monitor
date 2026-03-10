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


def test_build_app_uses_env_config(tmp_path, monkeypatch):
    from server_monitor.agent.main import build_app

    config_path = tmp_path / "agent.toml"
    config_path.write_text(
        "\n".join(
            [
                'server_id = "server-env"',
                'host = "127.0.0.1"',
                "port = 9000",
                "repo_paths = []",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("SERVER_MONITOR_AGENT_CONFIG", str(config_path))

    app = build_app()
    client = TestClient(app)
    response = client.get("/snapshot")
    assert response.status_code == 200
    assert response.json()["server_id"] == "server-env"
