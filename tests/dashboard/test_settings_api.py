from fastapi.testclient import TestClient


class _FakeGitRuntime:
    def __init__(self):
        self.calls = []
        self.fail_mode = None

    async def run_git_operation(self, *, server_id: str, repo_path: str, operation: str, branch: str | None = None):
        self.calls.append(
            {
                "server_id": server_id,
                "repo_path": repo_path,
                "operation": operation,
                "branch": branch,
            }
        )
        if self.fail_mode == "not_found":
            raise KeyError("unknown server")
        if self.fail_mode == "bad_request":
            raise ValueError("bad request")
        return {
            "ok": True,
            "operation": operation,
            "command": "git -C '/work/repo-a' fetch --prune --tags",
            "exit_code": 0,
            "stderr": "",
            "repo": {
                "path": repo_path,
                "branch": "main",
                "dirty": False,
                "ahead": 0,
                "behind": 0,
                "staged": 0,
                "unstaged": 0,
                "untracked": 0,
                "last_commit_age_seconds": 0,
            },
        }


def _make_client(tmp_path, runtime=None):
    from server_monitor.dashboard.api import create_dashboard_app
    from server_monitor.dashboard.settings import DashboardSettingsStore
    from server_monitor.dashboard.ws_hub import WebSocketHub

    store = DashboardSettingsStore(tmp_path / "servers.toml")
    app = create_dashboard_app(ws_hub=WebSocketHub(), settings_store=store, runtime=runtime)
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


def test_settings_api_git_ops_dispatches_to_runtime(tmp_path):
    runtime = _FakeGitRuntime()
    client = _make_client(tmp_path, runtime=runtime)

    client.post(
        "/api/servers",
        json={
            "server_id": "srv-c",
            "ssh_alias": "server-c",
            "working_dirs": ["/work/repo-c"],
            "enabled_panels": ["system", "gpu", "git", "clash"],
        },
    )

    response = client.post(
        "/api/servers/srv-c/git/ops",
        json={
            "repo_path": "/work/repo-c",
            "operation": "fetch",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["operation"] == "fetch"
    assert body["repo"]["path"] == "/work/repo-c"
    assert runtime.calls[0]["server_id"] == "srv-c"


def test_settings_api_git_ops_requires_runtime(tmp_path):
    client = _make_client(tmp_path)

    response = client.post(
        "/api/servers/srv-c/git/ops",
        json={
            "repo_path": "/work/repo-c",
            "operation": "fetch",
        },
    )
    assert response.status_code == 503


def test_settings_api_git_ops_maps_runtime_validation_errors(tmp_path):
    runtime = _FakeGitRuntime()
    runtime.fail_mode = "bad_request"
    client = _make_client(tmp_path, runtime=runtime)

    response = client.post(
        "/api/servers/srv-c/git/ops",
        json={
            "repo_path": "/work/not-allowed",
            "operation": "fetch",
        },
    )
    assert response.status_code == 400


def test_settings_api_git_ops_rejects_unknown_operation(tmp_path):
    runtime = _FakeGitRuntime()
    client = _make_client(tmp_path, runtime=runtime)

    response = client.post(
        "/api/servers/srv-c/git/ops",
        json={
            "repo_path": "/work/repo-c",
            "operation": "push",
        },
    )
    assert response.status_code == 400
    assert runtime.calls == []
