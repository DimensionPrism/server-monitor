from fastapi.testclient import TestClient


class _FakeGitRuntime:
    def __init__(self):
        self.calls = []
        self.open_terminal_calls = []
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

    async def open_repo_terminal(self, *, server_id: str, repo_path: str):
        self.open_terminal_calls.append(
            {
                "server_id": server_id,
                "repo_path": repo_path,
            }
        )
        if self.fail_mode == "not_found":
            raise KeyError("unknown server")
        if self.fail_mode == "bad_request":
            raise ValueError("repo not allowed")
        if self.fail_mode == "open_failed":
            raise RuntimeError("terminal launch failed")
        return {
            "ok": True,
            "launched_with": "x-terminal-emulator",
            "detail": "opened",
        }


class _FakeClashTunnelManager:
    def __init__(self):
        self.calls = []
        self.fail_mode = None

    async def open_ui_tunnel(self, *, server_id: str, ssh_alias: str, clash_ui_probe_url: str):
        self.calls.append(
            {
                "server_id": server_id,
                "ssh_alias": ssh_alias,
                "clash_ui_probe_url": clash_ui_probe_url,
            }
        )
        if self.fail_mode == "bad_request":
            raise ValueError("invalid clash ui url")
        if self.fail_mode == "open_failed":
            raise RuntimeError("ssh forward failed")
        return {
            "url": "http://127.0.0.1:19100/ui",
            "local_port": 19100,
            "reused": False,
        }


class _SecretProbeResult:
    def __init__(self, stdout: str, stderr: str = "", exit_code: int = 0, error: str | None = None):
        self.stdout = stdout
        self.stderr = stderr
        self.exit_code = exit_code
        self.error = error


class _SecretProbeExecutor:
    def __init__(self, stdout: str):
        self.stdout = stdout
        self.calls = []

    async def run(self, alias: str, remote_command: str, timeout_seconds: float | None = None):
        self.calls.append((alias, remote_command, timeout_seconds))
        return _SecretProbeResult(self.stdout)


class _RuntimeWithSecretProbe:
    def __init__(self, stdout: str):
        self.executor = _SecretProbeExecutor(stdout)


def _make_client(tmp_path, runtime=None, tunnel_manager=None):
    from server_monitor.dashboard.api import create_dashboard_app
    from server_monitor.dashboard.settings import DashboardSettingsStore
    from server_monitor.dashboard.ws_hub import WebSocketHub

    store = DashboardSettingsStore(tmp_path / "servers.toml")
    app = create_dashboard_app(
        ws_hub=WebSocketHub(),
        settings_store=store,
        runtime=runtime,
        clash_tunnel_manager=tunnel_manager,
    )
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
            "clash_api_probe_url": "http://127.0.0.1:9091/version",
            "clash_ui_probe_url": "http://127.0.0.1:9091/ui",
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
            "clash_api_probe_url": "http://127.0.0.1:9092/version",
            "clash_ui_probe_url": "http://127.0.0.1:9092/ui",
        },
    )
    assert update_resp.status_code == 200

    after_update = client.get("/api/settings").json()
    assert after_update["servers"][0]["ssh_alias"] == "server-a-updated"
    assert after_update["servers"][0]["enabled_panels"] == ["system", "git"]
    assert after_update["servers"][0]["clash_api_probe_url"] == "http://127.0.0.1:9092/version"
    assert after_update["servers"][0]["clash_ui_probe_url"] == "http://127.0.0.1:9092/ui"

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
    assert body["servers"][0]["clash_api_probe_url"] == "http://127.0.0.1:9090/version"
    assert body["servers"][0]["clash_ui_probe_url"] == "http://127.0.0.1:9090/ui"

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


def test_settings_api_open_terminal_dispatches_to_runtime(tmp_path):
    runtime = _FakeGitRuntime()
    client = _make_client(tmp_path, runtime=runtime)

    client.post(
        "/api/servers",
        json={
            "server_id": "srv-open",
            "ssh_alias": "server-open",
            "working_dirs": ["/work/repo-open"],
            "enabled_panels": ["git"],
        },
    )

    response = client.post(
        "/api/servers/srv-open/git/open-terminal",
        json={"repo_path": "/work/repo-open"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["launched_with"] == "x-terminal-emulator"
    assert runtime.open_terminal_calls == [{"server_id": "srv-open", "repo_path": "/work/repo-open"}]


def test_settings_api_open_terminal_requires_runtime(tmp_path):
    client = _make_client(tmp_path)

    response = client.post(
        "/api/servers/srv-open/git/open-terminal",
        json={"repo_path": "/work/repo-open"},
    )
    assert response.status_code == 503


def test_settings_api_open_terminal_maps_runtime_validation_errors(tmp_path):
    runtime = _FakeGitRuntime()
    runtime.fail_mode = "bad_request"
    client = _make_client(tmp_path, runtime=runtime)

    response = client.post(
        "/api/servers/srv-open/git/open-terminal",
        json={"repo_path": "/work/not-allowed"},
    )
    assert response.status_code == 400


def test_settings_api_open_terminal_maps_runtime_error(tmp_path):
    runtime = _FakeGitRuntime()
    runtime.fail_mode = "open_failed"
    client = _make_client(tmp_path, runtime=runtime)

    response = client.post(
        "/api/servers/srv-open/git/open-terminal",
        json={"repo_path": "/work/repo-open"},
    )
    assert response.status_code == 502


def test_settings_api_clash_tunnel_open_dispatches_to_manager(tmp_path):
    tunnel_manager = _FakeClashTunnelManager()
    client = _make_client(tmp_path, tunnel_manager=tunnel_manager)

    client.post(
        "/api/servers",
        json={
            "server_id": "srv-clash",
            "ssh_alias": "server-clash",
            "working_dirs": [],
            "enabled_panels": ["clash"],
            "clash_ui_probe_url": "http://127.0.0.1:9095/ui",
        },
    )

    response = client.post("/api/servers/srv-clash/clash/tunnel/open")

    assert response.status_code == 200
    body = response.json()
    assert body["url"] == "http://127.0.0.1:19100/ui"
    assert body["local_port"] == 19100
    assert body["reused"] is False
    assert tunnel_manager.calls[0]["server_id"] == "srv-clash"
    assert tunnel_manager.calls[0]["ssh_alias"] == "server-clash"
    assert tunnel_manager.calls[0]["clash_ui_probe_url"] == "http://127.0.0.1:9095/ui"


def test_settings_api_clash_tunnel_open_returns_secret_and_auto_login_url(tmp_path):
    tunnel_manager = _FakeClashTunnelManager()
    runtime = _RuntimeWithSecretProbe("😼 当前密钥：mysecret")
    client = _make_client(tmp_path, runtime=runtime, tunnel_manager=tunnel_manager)

    client.post(
        "/api/servers",
        json={
            "server_id": "srv-clash-secret",
            "ssh_alias": "server-clash-secret",
            "working_dirs": [],
            "enabled_panels": ["clash"],
            "clash_ui_probe_url": "http://127.0.0.1:9095/ui",
        },
    )

    response = client.post("/api/servers/srv-clash-secret/clash/tunnel/open")

    assert response.status_code == 200
    body = response.json()
    assert body["url"] == "http://127.0.0.1:19100/ui"
    assert body["secret"] == "mysecret"
    assert body["auto_login_url"] == "http://127.0.0.1:19100/ui/#/setup?hostname=127.0.0.1&port=19100&secret=mysecret"
    assert any("clashsecret" in call[1] for call in runtime.executor.calls)


def test_settings_api_clash_tunnel_open_requires_manager(tmp_path):
    client = _make_client(tmp_path)

    response = client.post("/api/servers/srv-clash/clash/tunnel/open")

    assert response.status_code == 503


def test_settings_api_clash_tunnel_open_maps_manager_validation_error(tmp_path):
    tunnel_manager = _FakeClashTunnelManager()
    tunnel_manager.fail_mode = "bad_request"
    client = _make_client(tmp_path, tunnel_manager=tunnel_manager)

    client.post(
        "/api/servers",
        json={
            "server_id": "srv-clash-invalid",
            "ssh_alias": "server-clash-invalid",
            "working_dirs": [],
            "enabled_panels": ["clash"],
            "clash_ui_probe_url": "not-a-url",
        },
    )

    response = client.post("/api/servers/srv-clash-invalid/clash/tunnel/open")

    assert response.status_code == 400


def test_settings_api_clash_tunnel_open_maps_manager_runtime_error(tmp_path):
    tunnel_manager = _FakeClashTunnelManager()
    tunnel_manager.fail_mode = "open_failed"
    client = _make_client(tmp_path, tunnel_manager=tunnel_manager)

    client.post(
        "/api/servers",
        json={
            "server_id": "srv-clash-fail",
            "ssh_alias": "server-clash-fail",
            "working_dirs": [],
            "enabled_panels": ["clash"],
        },
    )

    response = client.post("/api/servers/srv-clash-fail/clash/tunnel/open")

    assert response.status_code == 502
