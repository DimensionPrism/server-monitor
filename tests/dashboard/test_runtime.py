import asyncio
from dataclasses import dataclass
import time

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

        if "clashsecret" in remote_command:
            return _Result("😼 当前密钥：mysecret")
        if "nvidia-smi" in remote_command:
            return _Result("0, NVIDIA A100, 70, 1024, 40960, 50")
        if "git -C" in remote_command:
            return _Result("## main...origin/main\n M README.md\n")
        if "pgrep -f clash" in remote_command:
            return _Result("running=true\napi_reachable=false\nui_reachable=false\nmessage=ok")
        return _Result("CPU: 11.0\nMEM: 22.0\nDISK: 33.0\nRX_KBPS: 0\nTX_KBPS: 0")


class _FailFirstExecutor:
    def __init__(self):
        self.calls = []

    async def run(self, alias: str, remote_command: str):
        self.calls.append((alias, remote_command))
        if len(self.calls) == 1:
            return _Result("", stderr="ssh timeout", exit_code=255, error="timeout")
        return _Result("unexpected")


class _GitOpExecutor:
    def __init__(self):
        self.calls = []

    async def run(self, alias: str, remote_command: str):
        self.calls.append((alias, remote_command))
        if "fetch --prune --tags" in remote_command:
            return _Result("fetched")
        if "checkout" in remote_command:
            return _Result("switched")
        if "pull --ff-only" in remote_command:
            return _Result("up to date")
        if "status --porcelain --branch" in remote_command:
            return _Result("## main...origin/main [ahead 1]\n M README.md\n")
        return _Result("", stderr="unknown command", exit_code=1, error="unknown command")


class _FlakyGitStatusExecutor:
    def __init__(self):
        self.calls = []
        self._git_status_calls = 0

    async def run(self, alias: str, remote_command: str):
        self.calls.append((alias, remote_command))
        if "git -C" in remote_command:
            self._git_status_calls += 1
            if self._git_status_calls == 1:
                return _Result("## main...origin/main\n M README.md\n")
            return _Result("", stderr="temporary git status failure", exit_code=1, error="temporary git status failure")
        return _Result("")


class _TimeoutAwareGitExecutor:
    def __init__(self):
        self.calls = []

    async def run(self, alias: str, remote_command: str, timeout_seconds: float | None = None):
        self.calls.append((alias, remote_command, timeout_seconds))
        if "fetch --prune --tags" in remote_command and (timeout_seconds is None or timeout_seconds < 4.0):
            return _Result("", stderr="", exit_code=-1, error="timeout")
        if "status --porcelain --branch" in remote_command:
            return _Result("## main...origin/main\n")
        return _Result("ok")


class _DelayedExecutor:
    def __init__(self, delay_seconds: float = 0.2):
        self.delay_seconds = delay_seconds
        self.calls = []

    async def run(self, alias: str, remote_command: str, timeout_seconds: float | None = None):
        self.calls.append((alias, remote_command, timeout_seconds))
        await asyncio.sleep(self.delay_seconds)
        if "clashsecret" in remote_command:
            return _Result("😼 当前密钥：mysecret")
        if "nvidia-smi" in remote_command:
            return _Result("0, NVIDIA A100, 70, 1024, 40960, 50")
        if "git -C" in remote_command:
            return _Result("## main...origin/main\n M README.md\n")
        if "pgrep -f clash" in remote_command:
            return _Result("running=true\napi_reachable=false\nui_reachable=false\nmessage=ok")
        return _Result("CPU: 11.0\nMEM: 22.0\nDISK: 33.0\nRX_KBPS: 0\nTX_KBPS: 0")


class _FlakyMetricsExecutor:
    def __init__(self):
        self.calls = []
        self._system_calls = 0
        self._gpu_calls = 0

    async def run(self, alias: str, remote_command: str, timeout_seconds: float | None = None):
        self.calls.append((alias, remote_command, timeout_seconds))
        if "nvidia-smi" in remote_command:
            self._gpu_calls += 1
            if self._gpu_calls == 1:
                return _Result("0, NVIDIA A100, 70, 1024, 40960, 50")
            return _Result("", stderr="timeout", exit_code=-1, error="timeout")
        self._system_calls += 1
        if self._system_calls == 1:
            return _Result("CPU: 11.0\nMEM: 22.0\nDISK: 33.0\nRX_KBPS: 0\nTX_KBPS: 0")
        return _Result("", stderr="timeout", exit_code=-1, error="timeout")


class _SystemPollErrorExecutor:
    def __init__(self):
        self.calls = []

    async def run(self, alias: str, remote_command: str, timeout_seconds: float | None = None):
        self.calls.append((alias, remote_command, timeout_seconds))
        if "CPU=$(top -bn1" in remote_command:
            return _Result("", stderr="timeout", exit_code=-1, error="timeout")
        if "clashsecret" in remote_command:
            return _Result("😼 当前密钥：mysecret")
        if "nvidia-smi" in remote_command:
            return _Result("0, NVIDIA A100, 70, 1024, 40960, 50")
        if "git -C" in remote_command:
            return _Result("## main...origin/main\n M README.md\n")
        if "pgrep -f clash" in remote_command:
            return _Result("running=true\napi_reachable=false\nui_reachable=false\nmessage=ok")
        return _Result("")


class _MixedRepoFreshnessExecutor:
    def __init__(self):
        self.calls = []
        self._repo_fail_calls = 0

    async def run(self, alias: str, remote_command: str, timeout_seconds: float | None = None):
        self.calls.append((alias, remote_command, timeout_seconds))
        if "/work/repo-fail" in remote_command:
            self._repo_fail_calls += 1
            if self._repo_fail_calls >= 2:
                return _Result("", stderr="temporary git status failure", exit_code=1, error="temporary git status failure")
            return _Result("## main...origin/main\n M README.md\n")
        if "/work/repo-ok" in remote_command:
            return _Result("## main...origin/main\n M README.md\n")
        return _Result("", stderr="unknown command", exit_code=1, error="unknown command")


class _SecretAwareClashExecutor:
    def __init__(self):
        self.calls = []

    async def run(self, alias: str, remote_command: str, timeout_seconds: float | None = None):
        self.calls.append((alias, remote_command, timeout_seconds))
        if "clashsecret" in remote_command:
            return _Result("😼 当前密钥：mysecret")
        if "pgrep -f clash" in remote_command:
            return _Result("running=true\napi_reachable=true\nui_reachable=true\nmessage=ok")
        return _Result("")


class _MissingSecretClashExecutor:
    def __init__(self):
        self.calls = []

    async def run(self, alias: str, remote_command: str, timeout_seconds: float | None = None):
        self.calls.append((alias, remote_command, timeout_seconds))
        if "clashsecret" in remote_command:
            return _Result("no secret")
        if "pgrep -f clash" in remote_command:
            return _Result("running=true\napi_reachable=true\nui_reachable=true\nmessage=ok")
        return _Result("")


class _StallingStatusExecutor:
    def __init__(self, delay_seconds: float = 0.3):
        self.calls = []
        self.delay_seconds = delay_seconds

    async def run(self, alias: str, remote_command: str, timeout_seconds: float | None = None):
        self.calls.append((alias, remote_command, timeout_seconds))
        if "clashsecret" in remote_command:
            await asyncio.sleep(self.delay_seconds)
            return _Result("😼 当前密钥：mysecret")
        if "pgrep -f clash" in remote_command:
            return _Result("running=true\napi_reachable=true\nui_reachable=true\nmessage=ok")
        if "CPU=$(top -bn1" in remote_command:
            return _Result("CPU: 11.0\nMEM: 22.0\nDISK: 33.0\nRX_KBPS: 0\nTX_KBPS: 0")
        return _Result("")


class _SecretTimeoutAfterSuccessExecutor:
    def __init__(self):
        self.calls = []
        self._secret_calls = 0

    async def run(self, alias: str, remote_command: str, timeout_seconds: float | None = None):
        self.calls.append((alias, remote_command, timeout_seconds))
        if "clashsecret" in remote_command:
            self._secret_calls += 1
            if self._secret_calls == 1:
                return _Result("😼 当前密钥：mysecret")
            return _Result("", stderr="timeout", exit_code=-1, error="timeout")
        if "pgrep -f clash" in remote_command:
            return _Result("running=true\napi_reachable=true\nui_reachable=true\nmessage=ok")
        return _Result("")


class _ClashLocationExecutor:
    def __init__(self):
        self.calls = []

    async def run(self, alias: str, remote_command: str, timeout_seconds: float | None = None):
        self.calls.append((alias, remote_command, timeout_seconds))
        if "clashsecret" in remote_command:
            return _Result("😼 当前密钥：mysecret")
        if "pgrep -f clash" in remote_command:
            return _Result(
                "running=true\n"
                "api_reachable=true\n"
                "ui_reachable=true\n"
                "message=ok\n"
                "ip_location=Los Angeles, California, United States (1.2.3.4)"
            )
        return _Result("")


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


@pytest.mark.asyncio
async def test_runtime_short_circuits_when_ssh_unreachable():
    from server_monitor.dashboard.runtime import DashboardRuntime
    from server_monitor.dashboard.ws_hub import WebSocketHub

    settings = DashboardSettings(
        servers=[
            ServerSettings(
                server_id="server-c",
                ssh_alias="srv-c",
                working_dirs=["/work/repo-c"],
                enabled_panels=["system", "gpu", "git", "clash"],
            )
        ]
    )

    hub = WebSocketHub()
    ws = _FakeWebSocket()
    await hub.connect(ws)
    executor = _FailFirstExecutor()

    runtime = DashboardRuntime(
        hub=hub,
        settings_store=_FakeSettingsStore(settings),
        executor=executor,
    )

    await runtime.poll_once()

    assert len(executor.calls) <= 2
    assert not any("git -C" in call[1] for call in executor.calls)
    assert not any("pgrep -f clash" in call[1] for call in executor.calls)
    assert ws.messages[0]["snapshot"]["metadata"]["ssh_error"] != ""


@pytest.mark.asyncio
async def test_runtime_git_op_rejects_unknown_server():
    from server_monitor.dashboard.runtime import DashboardRuntime
    from server_monitor.dashboard.ws_hub import WebSocketHub

    settings = DashboardSettings(
        servers=[
            ServerSettings(
                server_id="server-d",
                ssh_alias="srv-d",
                working_dirs=["/work/repo-d"],
                enabled_panels=["git"],
            )
        ]
    )
    runtime = DashboardRuntime(
        hub=WebSocketHub(),
        settings_store=_FakeSettingsStore(settings),
        executor=_GitOpExecutor(),
    )

    with pytest.raises(KeyError):
        await runtime.run_git_operation(
            server_id="unknown",
            repo_path="/work/repo-d",
            operation="refresh",
        )


@pytest.mark.asyncio
async def test_runtime_git_op_rejects_repo_not_in_allowlist():
    from server_monitor.dashboard.runtime import DashboardRuntime
    from server_monitor.dashboard.ws_hub import WebSocketHub

    settings = DashboardSettings(
        servers=[
            ServerSettings(
                server_id="server-e",
                ssh_alias="srv-e",
                working_dirs=["/work/repo-e"],
                enabled_panels=["git"],
            )
        ]
    )
    runtime = DashboardRuntime(
        hub=WebSocketHub(),
        settings_store=_FakeSettingsStore(settings),
        executor=_GitOpExecutor(),
    )

    with pytest.raises(ValueError):
        await runtime.run_git_operation(
            server_id="server-e",
            repo_path="/work/not-allowed",
            operation="fetch",
        )


@pytest.mark.asyncio
async def test_runtime_git_op_fetch_returns_refreshed_repo_status():
    from server_monitor.dashboard.runtime import DashboardRuntime
    from server_monitor.dashboard.ws_hub import WebSocketHub

    settings = DashboardSettings(
        servers=[
            ServerSettings(
                server_id="server-f",
                ssh_alias="srv-f",
                working_dirs=["/work/repo-f"],
                enabled_panels=["git"],
            )
        ]
    )
    executor = _GitOpExecutor()
    runtime = DashboardRuntime(
        hub=WebSocketHub(),
        settings_store=_FakeSettingsStore(settings),
        executor=executor,
    )

    result = await runtime.run_git_operation(
        server_id="server-f",
        repo_path="/work/repo-f",
        operation="fetch",
    )

    assert result["ok"] is True
    assert result["operation"] == "fetch"
    assert result["repo"]["path"] == "/work/repo-f"
    assert result["repo"]["branch"] == "main"
    assert "fetch --prune --tags" in result["command"]
    assert any("status --porcelain --branch" in call[1] for call in executor.calls)


@pytest.mark.asyncio
async def test_runtime_open_repo_terminal_rejects_repo_not_in_allowlist():
    from server_monitor.dashboard.runtime import DashboardRuntime
    from server_monitor.dashboard.ws_hub import WebSocketHub

    settings = DashboardSettings(
        servers=[
            ServerSettings(
                server_id="server-open-e",
                ssh_alias="srv-open-e",
                working_dirs=["/work/repo-open-e"],
                enabled_panels=["git"],
            )
        ]
    )
    runtime = DashboardRuntime(
        hub=WebSocketHub(),
        settings_store=_FakeSettingsStore(settings),
        executor=_GitOpExecutor(),
        terminal_launcher=lambda **_: None,
    )

    with pytest.raises(ValueError):
        await runtime.open_repo_terminal(
            server_id="server-open-e",
            repo_path="/work/not-allowed",
        )


@pytest.mark.asyncio
async def test_runtime_open_repo_terminal_dispatches_to_launcher():
    from server_monitor.dashboard.runtime import DashboardRuntime
    from server_monitor.dashboard.ws_hub import WebSocketHub

    settings = DashboardSettings(
        servers=[
            ServerSettings(
                server_id="server-open-f",
                ssh_alias="srv-open-f",
                working_dirs=["/work/repo-open-f"],
                enabled_panels=["git"],
            )
        ]
    )

    calls = []

    def _fake_launcher(*, ssh_alias: str, repo_path: str):
        from server_monitor.dashboard.terminal_launcher import LaunchResult

        calls.append((ssh_alias, repo_path))
        return LaunchResult(ok=True, launched_with="x-terminal-emulator", detail="opened")

    runtime = DashboardRuntime(
        hub=WebSocketHub(),
        settings_store=_FakeSettingsStore(settings),
        executor=_GitOpExecutor(),
        terminal_launcher=_fake_launcher,
    )

    result = await runtime.open_repo_terminal(
        server_id="server-open-f",
        repo_path="/work/repo-open-f",
    )

    assert result["ok"] is True
    assert result["launched_with"] == "x-terminal-emulator"
    assert calls == [("srv-open-f", "/work/repo-open-f")]


@pytest.mark.asyncio
async def test_runtime_keeps_cached_repos_on_transient_git_poll_failure():
    from server_monitor.dashboard.runtime import DashboardRuntime
    from server_monitor.dashboard.ws_hub import WebSocketHub

    settings = DashboardSettings(
        metrics_interval_seconds=3.0,
        status_interval_seconds=0.0,
        servers=[
            ServerSettings(
                server_id="server-g",
                ssh_alias="srv-g",
                working_dirs=["/work/repo-g"],
                enabled_panels=["git"],
            )
        ],
    )

    hub = WebSocketHub()
    ws = _FakeWebSocket()
    await hub.connect(ws)
    executor = _FlakyGitStatusExecutor()

    runtime = DashboardRuntime(
        hub=hub,
        settings_store=_FakeSettingsStore(settings),
        executor=executor,
    )

    await runtime.poll_once()
    await runtime.poll_once()

    assert len(ws.messages) == 2
    assert len(ws.messages[0]["repos"]) == 1
    assert len(ws.messages[1]["repos"]) == 1
    assert ws.messages[1]["repos"][0]["path"] == "/work/repo-g"


@pytest.mark.asyncio
async def test_runtime_git_op_fetch_uses_extended_timeout():
    from server_monitor.dashboard.runtime import DashboardRuntime
    from server_monitor.dashboard.ws_hub import WebSocketHub

    settings = DashboardSettings(
        servers=[
            ServerSettings(
                server_id="server-h",
                ssh_alias="srv-h",
                working_dirs=["/work/repo-h"],
                enabled_panels=["git"],
            )
        ]
    )
    executor = _TimeoutAwareGitExecutor()
    runtime = DashboardRuntime(
        hub=WebSocketHub(),
        settings_store=_FakeSettingsStore(settings),
        executor=executor,
    )

    result = await runtime.run_git_operation(
        server_id="server-h",
        repo_path="/work/repo-h",
        operation="fetch",
    )

    assert result["ok"] is True
    fetch_calls = [call for call in executor.calls if "fetch --prune --tags" in call[1]]
    assert len(fetch_calls) == 1
    assert fetch_calls[0][2] is not None
    assert fetch_calls[0][2] >= 10.0


@pytest.mark.asyncio
async def test_runtime_polls_servers_in_parallel():
    from server_monitor.dashboard.runtime import DashboardRuntime
    from server_monitor.dashboard.ws_hub import WebSocketHub

    settings = DashboardSettings(
        metrics_interval_seconds=3.0,
        status_interval_seconds=30.0,
        servers=[
            ServerSettings(
                server_id="server-p1",
                ssh_alias="srv-p1",
                working_dirs=[],
                enabled_panels=["system"],
            ),
            ServerSettings(
                server_id="server-p2",
                ssh_alias="srv-p2",
                working_dirs=[],
                enabled_panels=["system"],
            ),
        ],
    )

    runtime = DashboardRuntime(
        hub=WebSocketHub(),
        settings_store=_FakeSettingsStore(settings),
        executor=_DelayedExecutor(delay_seconds=0.2),
    )

    start = time.monotonic()
    await runtime.poll_once()
    elapsed = time.monotonic() - start

    assert elapsed < 0.35


@pytest.mark.asyncio
async def test_runtime_polls_git_repos_in_parallel():
    from server_monitor.dashboard.runtime import DashboardRuntime
    from server_monitor.dashboard.ws_hub import WebSocketHub

    settings = DashboardSettings(
        metrics_interval_seconds=3.0,
        status_interval_seconds=0.0,
        servers=[
            ServerSettings(
                server_id="server-gp",
                ssh_alias="srv-gp",
                working_dirs=[
                    "/work/repo-1",
                    "/work/repo-2",
                    "/work/repo-3",
                    "/work/repo-4",
                ],
                enabled_panels=["git"],
            )
        ],
    )

    runtime = DashboardRuntime(
        hub=WebSocketHub(),
        settings_store=_FakeSettingsStore(settings),
        executor=_DelayedExecutor(delay_seconds=0.2),
    )

    start = time.monotonic()
    await runtime.poll_once()
    elapsed = time.monotonic() - start

    assert elapsed < 0.45


def test_metrics_sleep_seconds_compensates_poll_time():
    from server_monitor.dashboard.runtime import _metrics_sleep_seconds

    assert _metrics_sleep_seconds(interval_seconds=1.0, elapsed_seconds=0.25) == pytest.approx(0.75)
    assert _metrics_sleep_seconds(interval_seconds=1.0, elapsed_seconds=1.6) == pytest.approx(0.05)


@pytest.mark.asyncio
async def test_runtime_keeps_cached_system_and_gpu_on_transient_metric_failure():
    from server_monitor.dashboard.runtime import DashboardRuntime
    from server_monitor.dashboard.ws_hub import WebSocketHub

    settings = DashboardSettings(
        metrics_interval_seconds=1.0,
        status_interval_seconds=10.0,
        servers=[
            ServerSettings(
                server_id="server-m1",
                ssh_alias="srv-m1",
                working_dirs=[],
                enabled_panels=["system", "gpu"],
            )
        ],
    )

    hub = WebSocketHub()
    ws = _FakeWebSocket()
    await hub.connect(ws)

    runtime = DashboardRuntime(
        hub=hub,
        settings_store=_FakeSettingsStore(settings),
        executor=_FlakyMetricsExecutor(),
    )

    await runtime.poll_once()
    await runtime.poll_once()

    assert len(ws.messages) == 2
    first = ws.messages[0]["snapshot"]
    second = ws.messages[1]["snapshot"]

    assert first["cpu_percent"] == 11.0
    assert len(first["gpus"]) == 1
    assert second["cpu_percent"] == 11.0
    assert len(second["gpus"]) == 1
    assert second["metadata"]["metrics_error"] == "timeout"
    assert second["metadata"]["gpu_error"] == "timeout"


@pytest.mark.asyncio
async def test_runtime_emits_last_updated_timestamps_for_all_panels_and_repos():
    from server_monitor.dashboard.runtime import DashboardRuntime
    from server_monitor.dashboard.ws_hub import WebSocketHub

    settings = DashboardSettings(
        metrics_interval_seconds=1.0,
        status_interval_seconds=0.0,
        servers=[
            ServerSettings(
                server_id="server-ts",
                ssh_alias="srv-ts",
                working_dirs=["/work/repo-ts"],
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

    payload = ws.messages[0]
    snapshot = payload["snapshot"]
    metadata = snapshot["metadata"]

    assert isinstance(metadata["system_last_updated_at"], str)
    assert isinstance(metadata["gpu_last_updated_at"], str)
    assert isinstance(payload["clash"]["last_updated_at"], str)
    assert isinstance(payload["repos"][0]["last_updated_at"], str)


@pytest.mark.asyncio
async def test_runtime_keeps_repo_last_updated_timestamp_when_repo_uses_cache():
    from server_monitor.dashboard.runtime import DashboardRuntime
    from server_monitor.dashboard.ws_hub import WebSocketHub

    settings = DashboardSettings(
        metrics_interval_seconds=1.0,
        status_interval_seconds=0.0,
        servers=[
            ServerSettings(
                server_id="server-ts-git",
                ssh_alias="srv-ts-git",
                working_dirs=["/work/repo-ts-git"],
                enabled_panels=["git"],
            )
        ],
    )

    hub = WebSocketHub()
    ws = _FakeWebSocket()
    await hub.connect(ws)

    runtime = DashboardRuntime(
        hub=hub,
        settings_store=_FakeSettingsStore(settings),
        executor=_FlakyGitStatusExecutor(),
    )

    await runtime.poll_once()
    await runtime.poll_once()

    first_ts = ws.messages[0]["repos"][0]["last_updated_at"]
    second_ts = ws.messages[1]["repos"][0]["last_updated_at"]
    assert isinstance(first_ts, str)
    assert second_ts == first_ts


@pytest.mark.asyncio
async def test_runtime_emits_panel_freshness_live_on_success():
    from server_monitor.dashboard.runtime import DashboardRuntime
    from server_monitor.dashboard.ws_hub import WebSocketHub

    settings = DashboardSettings(
        metrics_interval_seconds=1.0,
        status_interval_seconds=0.0,
        servers=[
            ServerSettings(
                server_id="server-fresh-live",
                ssh_alias="srv-fresh-live",
                working_dirs=["/work/repo-fresh-live"],
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

    payload = ws.messages[0]
    assert payload["freshness"]["system"]["state"] == "live"
    assert payload["freshness"]["gpu"]["state"] == "live"
    assert payload["freshness"]["git"]["state"] == "live"
    assert payload["freshness"]["clash"]["state"] == "live"


@pytest.mark.asyncio
async def test_runtime_marks_system_freshness_cached_on_poll_error():
    from server_monitor.dashboard.runtime import DashboardRuntime
    from server_monitor.dashboard.ws_hub import WebSocketHub

    settings = DashboardSettings(
        metrics_interval_seconds=1.0,
        status_interval_seconds=10.0,
        servers=[
            ServerSettings(
                server_id="server-fresh-system-error",
                ssh_alias="srv-fresh-system-error",
                working_dirs=[],
                enabled_panels=["system"],
            )
        ],
    )

    hub = WebSocketHub()
    ws = _FakeWebSocket()
    await hub.connect(ws)

    runtime = DashboardRuntime(
        hub=hub,
        settings_store=_FakeSettingsStore(settings),
        executor=_SystemPollErrorExecutor(),
    )

    await runtime.poll_once()

    payload = ws.messages[0]
    assert payload["freshness"]["system"]["state"] == "cached"
    assert payload["freshness"]["system"]["reason"] == "poll_error"


@pytest.mark.asyncio
async def test_runtime_marks_repo_freshness_mixed_live_and_cached():
    from server_monitor.dashboard.runtime import DashboardRuntime
    from server_monitor.dashboard.ws_hub import WebSocketHub

    settings = DashboardSettings(
        metrics_interval_seconds=1.0,
        status_interval_seconds=0.0,
        servers=[
            ServerSettings(
                server_id="server-fresh-repos",
                ssh_alias="srv-fresh-repos",
                working_dirs=["/work/repo-ok", "/work/repo-fail"],
                enabled_panels=["git"],
            )
        ],
    )

    hub = WebSocketHub()
    ws = _FakeWebSocket()
    await hub.connect(ws)
    executor = _MixedRepoFreshnessExecutor()

    runtime = DashboardRuntime(
        hub=hub,
        settings_store=_FakeSettingsStore(settings),
        executor=executor,
    )

    await runtime.poll_once()
    await runtime.poll_once()

    payload = ws.messages[1]
    repos = {repo["path"]: repo for repo in payload["repos"]}
    assert repos["/work/repo-ok"]["freshness"]["state"] == "live"
    assert repos["/work/repo-fail"]["freshness"]["state"] == "cached"
    assert repos["/work/repo-fail"]["freshness"]["reason"] == "poll_error"


def test_extract_clash_secret_parses_chinese_label_output():
    from server_monitor.dashboard.runtime import _extract_clash_secret

    text = "😼 当前密钥：mysecret"
    assert _extract_clash_secret(text) == "mysecret"


def test_clash_secret_command_includes_runtime_yaml_fallback():
    from server_monitor.dashboard.runtime import _clash_secret_command

    cmd = _clash_secret_command()
    assert "clashsecret" in cmd
    assert "runtime.yaml" in cmd
    assert "当前密钥" in cmd


def test_clash_command_includes_bearer_header_for_api_and_ui():
    from server_monitor.dashboard.runtime import _clash_command

    cmd = _clash_command(
        api_probe_url="http://127.0.0.1:9090/version",
        ui_probe_url="http://127.0.0.1:9090/ui",
        secret="mysecret",
    )
    assert "Authorization: Bearer mysecret" in cmd
    assert cmd.count("-H \"$AUTH_HEADER\"") >= 2
    assert "127.0.0.1:9090/version" in cmd
    assert "127.0.0.1:9090/ui" in cmd
    assert "-lt 400" in cmd
    assert "ip_location=" in cmd


@pytest.mark.asyncio
async def test_runtime_clash_probe_uses_secret_command_each_status_cycle():
    from server_monitor.dashboard.runtime import DashboardRuntime
    from server_monitor.dashboard.ws_hub import WebSocketHub

    settings = DashboardSettings(
        metrics_interval_seconds=3.0,
        status_interval_seconds=0.0,
        servers=[
            ServerSettings(
                server_id="server-clash-secret-cycle",
                ssh_alias="srv-clash-secret-cycle",
                working_dirs=[],
                enabled_panels=["clash"],
            )
        ],
    )

    hub = WebSocketHub()
    ws = _FakeWebSocket()
    await hub.connect(ws)
    executor = _SecretAwareClashExecutor()
    runtime = DashboardRuntime(
        hub=hub,
        settings_store=_FakeSettingsStore(settings),
        executor=executor,
    )

    await runtime.poll_once()
    await runtime.poll_once()

    secret_calls = [call for call in executor.calls if "clashsecret" in call[1]]
    assert len(secret_calls) >= 2


@pytest.mark.asyncio
async def test_runtime_clash_probe_sets_unreachable_when_secret_unavailable():
    from server_monitor.dashboard.runtime import DashboardRuntime
    from server_monitor.dashboard.ws_hub import WebSocketHub

    settings = DashboardSettings(
        metrics_interval_seconds=3.0,
        status_interval_seconds=0.0,
        servers=[
            ServerSettings(
                server_id="server-clash-secret-missing",
                ssh_alias="srv-clash-secret-missing",
                working_dirs=[],
                enabled_panels=["clash"],
            )
        ],
    )

    hub = WebSocketHub()
    ws = _FakeWebSocket()
    await hub.connect(ws)
    runtime = DashboardRuntime(
        hub=hub,
        settings_store=_FakeSettingsStore(settings),
        executor=_MissingSecretClashExecutor(),
    )

    await runtime.poll_once()

    payload = ws.messages[0]
    assert payload["clash"]["api_reachable"] is False
    assert payload["clash"]["ui_reachable"] is False
    assert payload["clash"]["message"] == "secret-unavailable"


@pytest.mark.asyncio
async def test_runtime_status_stall_does_not_block_poll_once():
    from server_monitor.dashboard.runtime import DashboardRuntime
    from server_monitor.dashboard.ws_hub import WebSocketHub

    settings = DashboardSettings(
        metrics_interval_seconds=1.0,
        status_interval_seconds=0.0,
        servers=[
            ServerSettings(
                server_id="server-status-stall",
                ssh_alias="srv-status-stall",
                working_dirs=[],
                enabled_panels=["system", "clash"],
            )
        ],
    )

    runtime = DashboardRuntime(
        hub=WebSocketHub(),
        settings_store=_FakeSettingsStore(settings),
        executor=_StallingStatusExecutor(delay_seconds=0.3),
    )

    start = time.monotonic()
    await runtime.poll_once()
    elapsed = time.monotonic() - start

    assert elapsed < 0.2
    await runtime.stop()


@pytest.mark.asyncio
async def test_runtime_keeps_cached_clash_when_secret_command_times_out():
    from server_monitor.dashboard.runtime import DashboardRuntime
    from server_monitor.dashboard.ws_hub import WebSocketHub

    settings = DashboardSettings(
        metrics_interval_seconds=1.0,
        status_interval_seconds=0.0,
        servers=[
            ServerSettings(
                server_id="server-clash-secret-timeout",
                ssh_alias="srv-clash-secret-timeout",
                working_dirs=[],
                enabled_panels=["clash"],
            )
        ],
    )

    hub = WebSocketHub()
    ws = _FakeWebSocket()
    await hub.connect(ws)
    runtime = DashboardRuntime(
        hub=hub,
        settings_store=_FakeSettingsStore(settings),
        executor=_SecretTimeoutAfterSuccessExecutor(),
    )

    await runtime.poll_once()
    assert ws.messages[0]["clash"]["message"] == "ok"

    await runtime.poll_once()
    await asyncio.sleep(0.01)
    await runtime.poll_once()

    latest = ws.messages[-1]["clash"]
    assert latest["api_reachable"] is True
    assert latest["ui_reachable"] is True


@pytest.mark.asyncio
async def test_runtime_clash_payload_contains_ip_location():
    from server_monitor.dashboard.runtime import DashboardRuntime
    from server_monitor.dashboard.ws_hub import WebSocketHub

    settings = DashboardSettings(
        metrics_interval_seconds=1.0,
        status_interval_seconds=0.0,
        servers=[
            ServerSettings(
                server_id="server-clash-location",
                ssh_alias="srv-clash-location",
                working_dirs=[],
                enabled_panels=["clash"],
            )
        ],
    )

    hub = WebSocketHub()
    ws = _FakeWebSocket()
    await hub.connect(ws)
    runtime = DashboardRuntime(
        hub=hub,
        settings_store=_FakeSettingsStore(settings),
        executor=_ClashLocationExecutor(),
    )

    await runtime.poll_once()

    payload = ws.messages[0]
    assert payload["clash"]["ip_location"] == "Los Angeles, California, United States (1.2.3.4)"
    assert payload["clash"]["message"] == "ok"
    await runtime.stop()
