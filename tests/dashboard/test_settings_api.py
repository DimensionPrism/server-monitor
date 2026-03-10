from fastapi.testclient import TestClient


def _make_client(tmp_path):
    from server_monitor.dashboard.api import create_dashboard_app
    from server_monitor.dashboard.settings import DashboardSettingsStore
    from server_monitor.dashboard.ws_hub import WebSocketHub

    store = DashboardSettingsStore(tmp_path / "servers.toml")
    app = create_dashboard_app(ws_hub=WebSocketHub(), settings_store=store)
    return TestClient(app)


def test_settings_api_crud_server(tmp_path):
    client = _make_client(tmp_path)

    initial = client.get("/api/settings")
    assert initial.status_code == 200
    assert initial.json()["servers"] == []

    create_resp = client.post(
        "/api/servers",
        json={
            "server_id": "srv-a",
            "ssh_alias": "server-a",
            "working_dirs": ["/work/repo-a"],
            "enabled_panels": ["system", "gpu", "git", "clash"],
        },
    )
    assert create_resp.status_code == 201

    update_resp = client.put(
        "/api/servers/srv-a",
        json={
            "server_id": "srv-a",
            "ssh_alias": "server-a-updated",
            "working_dirs": ["/work/repo-a"],
            "enabled_panels": ["system", "git"],
        },
    )
    assert update_resp.status_code == 200

    after_update = client.get("/api/settings").json()
    assert after_update["servers"][0]["ssh_alias"] == "server-a-updated"
    assert after_update["servers"][0]["enabled_panels"] == ["system", "git"]

    delete_resp = client.delete("/api/servers/srv-a")
    assert delete_resp.status_code == 204
    assert client.get("/api/settings").json()["servers"] == []


def test_settings_api_working_dir_and_panel_updates(tmp_path):
    client = _make_client(tmp_path)

    client.post(
        "/api/servers",
        json={
            "server_id": "srv-b",
            "ssh_alias": "server-b",
            "working_dirs": [],
            "enabled_panels": ["system", "gpu", "git", "clash"],
        },
    )

    add_dir = client.post("/api/servers/srv-b/working-dirs", json={"path": "/work/repo-b"})
    assert add_dir.status_code == 200

    set_panels = client.put(
        "/api/servers/srv-b/panels",
        json={"enabled_panels": ["system", "git"]},
    )
    assert set_panels.status_code == 200

    body = client.get("/api/settings").json()
    assert body["servers"][0]["working_dirs"] == ["/work/repo-b"]
    assert body["servers"][0]["enabled_panels"] == ["system", "git"]

    remove_dir = client.request("DELETE", "/api/servers/srv-b/working-dirs", json={"path": "/work/repo-b"})
    assert remove_dir.status_code == 200
    assert client.get("/api/settings").json()["servers"][0]["working_dirs"] == []
