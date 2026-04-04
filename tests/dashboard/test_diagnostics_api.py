from fastapi.testclient import TestClient

import asyncio


class _NoopExecutor:
    async def run(
        self, alias: str, remote_command: str, timeout_seconds: float | None = None
    ):
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
    from server_monitor.dashboard.health import CommandHealthRecord, CommandKind
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


def test_diagnostics_endpoint_includes_metrics_stream_status(tmp_path):
    from server_monitor.dashboard.metrics.protocol import MetricsStreamSample
    from server_monitor.dashboard.runtime import DashboardRuntime
    from server_monitor.dashboard.settings import ServerSettings
    from server_monitor.dashboard.ws_hub import WebSocketHub

    client, store = _make_client(tmp_path)
    store.create_server(
        ServerSettings(
            server_id="srv-stream",
            ssh_alias="server-stream",
            enabled_panels=["system", "gpu"],
        )
    )
    runtime = DashboardRuntime(
        hub=WebSocketHub(),
        settings_store=store,
        executor=_NoopExecutor(),
    )
    asyncio.run(
        runtime._handle_metrics_stream_sample(
            "srv-stream",
            MetricsStreamSample(
                sequence=1,
                server_time="2026-03-12T12:00:00+00:00",
                sample_interval_ms=250,
                cpu_percent=11.0,
                memory_percent=22.0,
                disk_percent=33.0,
                network_rx_kbps=44.0,
                network_tx_kbps=55.0,
                gpus=[],
            ),
        )
    )
    asyncio.run(
        runtime._handle_metrics_stream_state_change("srv-stream", "reconnecting")
    )
    client, _ = _make_client(tmp_path, runtime=runtime)

    response = client.get("/api/diagnostics")

    assert response.status_code == 200
    body = response.json()
    assert body["servers"][0]["server_id"] == "srv-stream"
    assert body["servers"][0]["metrics_stream"]["state"] == "reconnecting"
    assert body["servers"][0]["metrics_stream"]["last_sequence"] == 1
    assert body["servers"][0]["metrics_stream"]["reconnect_count"] == 1
    assert (
        body["servers"][0]["metrics_stream"]["last_sample_server_time"]
        == "2026-03-12T12:00:00+00:00"
    )
