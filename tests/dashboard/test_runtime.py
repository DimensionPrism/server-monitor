from dataclasses import dataclass

import pytest

from server_monitor.dashboard.settings import DashboardSettings, ServerSettings


class _FakeWebSocket:
    def __init__(self):
        self.messages = []

    async def send_json(self, payload):
        self.messages.append(payload)


class _FakeSettingsStore:
    def __init__(self, settings: DashboardSettings):
        self._settings = settings

    def load(self) -> DashboardSettings:
        return self._settings


@dataclass
class _Result:
    stdout: str
    stderr: str = ""
    exit_code: int = 0
    error: str | None = None


class _FakeExecutor:
    def __init__(self):
        self.calls = []

    async def run(self, alias: str, remote_command: str):
        self.calls.append((alias, remote_command))

        if "nvidia-smi" in remote_command:
            return _Result("0, NVIDIA A100, 70, 1024, 40960, 50")
        if "git -C" in remote_command:
            return _Result("## main...origin/main\n M README.md\n")
        if "pgrep -f clash" in remote_command:
            return _Result("running=true\napi_reachable=false\nui_reachable=false\nmessage=ok")
        return _Result("CPU: 11.0\nMEM: 22.0\nDISK: 33.0\nRX_KBPS: 0\nTX_KBPS: 0")


@pytest.mark.asyncio
async def test_runtime_poll_once_broadcasts_agentless_update():
    from server_monitor.dashboard.runtime import DashboardRuntime
    from server_monitor.dashboard.ws_hub import WebSocketHub

    settings = DashboardSettings(
        metrics_interval_seconds=3.0,
        status_interval_seconds=10.0,
        servers=[
            ServerSettings(
                server_id="server-a",
                ssh_alias="srv-a",
                working_dirs=["/work/repo-a"],
                enabled_panels=["system", "gpu", "git", "clash"],
            )
        ],
    )

    hub = WebSocketHub()
    ws = _FakeWebSocket()
    await hub.connect(ws)

    runtime = DashboardRuntime(
        hub=hub,
        settings_store=_FakeSettingsStore(settings),
        executor=_FakeExecutor(),
    )

    await runtime.poll_once()

    assert len(ws.messages) == 1
    payload = ws.messages[0]
    assert payload["server_id"] == "server-a"
    assert payload["snapshot"]["cpu_percent"] == 11.0
    assert payload["snapshot"]["gpus"][0]["index"] == 0
    assert payload["clash"]["running"] is True
    assert payload["enabled_panels"] == ["system", "gpu", "git", "clash"]


@pytest.mark.asyncio
async def test_runtime_respects_panel_toggles():
    from server_monitor.dashboard.runtime import DashboardRuntime
    from server_monitor.dashboard.ws_hub import WebSocketHub

    settings = DashboardSettings(
        metrics_interval_seconds=3.0,
        status_interval_seconds=10.0,
        servers=[
            ServerSettings(
                server_id="server-b",
                ssh_alias="srv-b",
                working_dirs=["/work/repo-b"],
                enabled_panels=["system"],
            )
        ],
    )

    executor = _FakeExecutor()
    runtime = DashboardRuntime(
        hub=WebSocketHub(),
        settings_store=_FakeSettingsStore(settings),
        executor=executor,
    )

    await runtime.poll_once()

    assert len(executor.calls) == 1
    assert "nvidia-smi" not in executor.calls[0][1]
