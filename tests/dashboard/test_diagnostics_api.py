from fastapi.testclient import TestClient


class _NoopExecutor:
    async def run(self, alias: str, remote_command: str, timeout_seconds: float | None = None):
        raise AssertionError("executor should not be used in diagnostics api tests")


def _make_client(tmp_path, runtime=None):
    from server_monitor.dashboard.api import create_dashboard_app
    from server_monitor.dashboard.settings import DashboardSettingsStore
    from server_monitor.dashboard.ws_hub import WebSocketHub

    store = DashboardSettingsStore(tmp_path / "servers.toml")
    app = create_dashboard_app(
        ws_hub=WebSocketHub(),
        settings_store=store,
        runtime=runtime,
    )
    return TestClient(app), store


def test_diagnostics_endpoint_returns_empty_bundle_when_no_records(tmp_path):
    from server_monitor.dashboard.runtime import DashboardRuntime
    from server_monitor.dashboard.ws_hub import WebSocketHub

    client, store = _make_client(tmp_path)
    runtime = DashboardRuntime(
        hub=WebSocketHub(),
        settings_store=store,
        executor=_NoopExecutor(),
    )
    client, _ = _make_client(tmp_path, runtime=runtime)

    response = client.get("/api/diagnostics")

    assert response.status_code == 200
    body = response.json()
    assert body["servers"] == []
    assert body["settings"]["servers"] == []


def test_diagnostics_endpoint_redacts_clash_secret(tmp_path):
    from server_monitor.dashboard.command_policy import CommandHealthRecord, CommandKind
    from server_monitor.dashboard.runtime import DashboardRuntime
    from server_monitor.dashboard.settings import ServerSettings
    from server_monitor.dashboard.ws_hub import WebSocketHub

    client, store = _make_client(tmp_path)
    store.create_server(
        ServerSettings(
            server_id="srv-secret",
            ssh_alias="server-secret",
            enabled_panels=["clash"],
        )
    )
    runtime = DashboardRuntime(
        hub=WebSocketHub(),
        settings_store=store,
        executor=_NoopExecutor(),
    )
    runtime._append_command_health(
        CommandHealthRecord(
            recorded_at="2026-03-11T10:00:00+00:00",
            server_id="srv-secret",
            command_kind=CommandKind.CLASH_PROBE,
            target_label="server",
            ok=False,
            failure_class="nonzero_exit",
            attempt_count=1,
            duration_ms=25,
            attempt_durations_ms=[25],
            exit_code=1,
            cooldown_applied=False,
            cache_used=False,
            message="Authorization: Bearer mysecret",
        )
    )
    client, _ = _make_client(tmp_path, runtime=runtime)

    response = client.get("/api/diagnostics")

    assert response.status_code == 200
    assert "mysecret" not in response.text
    body = response.json()
    assert body["servers"][0]["server_id"] == "srv-secret"


def test_diagnostics_endpoint_requires_runtime_support(tmp_path):
    client, _ = _make_client(tmp_path)

    response = client.get("/api/diagnostics")

    assert response.status_code == 503
