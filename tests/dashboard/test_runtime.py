import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import re
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


class _FakeMetricsStreamManager:
    def __init__(self):
        self.started_with = []
        self.stopped = False
        self._on_sample = None
        self._on_state_change = None

    def bind(self, *, on_sample, on_state_change) -> None:
        self._on_sample = on_sample
        self._on_state_change = on_state_change

    async def start(self, servers) -> None:
        self.started_with.append(list(servers))

    async def stop(self) -> None:
        self.stopped = True

    async def emit_sample(self, server_id: str, sample) -> None:
        assert self._on_sample is not None
        await self._on_sample(server_id, sample)

    async def emit_state(self, server_id: str, state: str) -> None:
        assert self._on_state_change is not None
        await self._on_state_change(server_id, state)


class _FakeSyncingMetricsStreamManager(_FakeMetricsStreamManager):
    def __init__(self):
        super().__init__()
        self.sync_calls = []

    async def sync_servers(self, servers) -> None:
        self.sync_calls.append(list(servers))


@dataclass
class _Result:
    stdout: str
    stderr: str = ""
    exit_code: int = 0
    error: str | None = None


class _FakeExecutor:
    def __init__(self):
        self.calls = []

    async def run(self, alias: str, remote_command: str, timeout_seconds: float | None = None):
        self.calls.append((alias, remote_command, timeout_seconds))

        if "SMTOKEN BEGIN kind=system target=server" in remote_command and "nvidia-smi" in remote_command:
            return _Result(
                "SMTOKEN BEGIN kind=system target=server exit=0 duration_ms=111 stream=stdout\n"
                "CPU: 11.0\n"
                "MEM: 22.0\n"
                "DISK: 33.0\n"
                "RX_KBPS: 0\n"
                "TX_KBPS: 0\n"
                "SMTOKEN END\n"
                "SMTOKEN BEGIN kind=gpu target=server exit=0 duration_ms=98 stream=stdout\n"
                "0, NVIDIA A100, 70, 1024, 40960, 50\n"
                "SMTOKEN END\n"
            )
        if "SMTOKEN BEGIN kind=git_status target=" in remote_command and "SMTOKEN BEGIN kind=clash_secret target=server" in remote_command:
            repo_paths = re.findall(r"kind=git_status target=([^ ]+)", remote_command)
            repo_sections = "".join(
                _batch_stdout_section(
                    kind="git_status",
                    target=repo_path,
                    payload="## main...origin/main\n M README.md\n",
                    duration_ms=120,
                )
                for repo_path in repo_paths
            )
            return _Result(
                repo_sections
                + _batch_stdout_section(
                    kind="clash_secret",
                    target="server",
                    payload="😼 当前密钥：mysecret\n",
                    duration_ms=90,
                )
                + _batch_stdout_section(
                    kind="clash_probe",
                    target="server",
                    payload="running=true\napi_reachable=true\nui_reachable=true\nmessage=ok\n",
                    duration_ms=95,
                )
            )
        if "clashsecret" in remote_command:
            return _Result("😼 当前密钥：mysecret")
        if "nvidia-smi" in remote_command:
            return _Result("0, NVIDIA A100, 70, 1024, 40960, 50")
        if "git -C" in remote_command:
            return _Result("## main...origin/main\n M README.md\n")
        if "pgrep -f clash" in remote_command:
            return _Result("running=true\napi_reachable=false\nui_reachable=false\nmessage=ok")
        return _Result("CPU: 11.0\nMEM: 22.0\nDISK: 33.0\nRX_KBPS: 0\nTX_KBPS: 0")


class _HostUnreachableExecutor:
    def __init__(self):
        self.calls = []

    async def run(self, alias: str, remote_command: str):
        self.calls.append((alias, remote_command))
        return _Result("", stderr="ssh timeout", exit_code=255, error="timeout")


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


class _GitOpBatchTransport:
    def __init__(self):
        self.calls = []

    async def run(self, alias: str, remote_command: str, *, timeout_seconds: float):
        self.calls.append((alias, remote_command, timeout_seconds))
        if "fetch --prune --tags" in remote_command:
            return _Result("fetched")
        if "pull --ff-only" in remote_command:
            return _Result("Already up to date.\n")
        if "checkout" in remote_command:
            return _Result("Already on 'main'\n")
        if "status --porcelain --branch" in remote_command:
            return _Result("## main...origin/main [behind 2]\n")
        return _Result("", stderr="unknown command", exit_code=1, error="unknown command")


class _FailingGitOpBatchTransport:
    def __init__(self):
        self.calls = []

    async def run(self, alias: str, remote_command: str, *, timeout_seconds: float):
        self.calls.append((alias, remote_command, timeout_seconds))
        raise RuntimeError("persistent transport failed")


class _SlowGitStatusExecutor:
    def __init__(self):
        self.calls = []

    async def run(self, alias: str, remote_command: str, timeout_seconds: float | None = None):
        self.calls.append((alias, remote_command, timeout_seconds))
        if "status --porcelain --branch" in remote_command:
            if timeout_seconds is None or timeout_seconds < 5.0:
                return _Result("", stderr="", exit_code=-1, error="timeout")
            return _Result("## main...origin/main\n")
        return _Result("")


class _VerySlowGitStatusExecutor:
    def __init__(self):
        self.calls = []

    async def run(self, alias: str, remote_command: str, timeout_seconds: float | None = None):
        self.calls.append((alias, remote_command, timeout_seconds))
        if "status --porcelain --branch" in remote_command:
            if timeout_seconds is None or timeout_seconds < 10.0:
                return _Result("", stderr="", exit_code=-1, error="timeout")
            return _Result("## main...origin/main\n")
        return _Result("")


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
        self._metrics_batch_calls = 0

    async def run(self, alias: str, remote_command: str, timeout_seconds: float | None = None):
        self.calls.append((alias, remote_command, timeout_seconds))
        if "SMTOKEN BEGIN kind=system target=server" in remote_command and "nvidia-smi" in remote_command:
            self._metrics_batch_calls += 1
            if self._metrics_batch_calls == 1:
                return _Result(
                    "SMTOKEN BEGIN kind=system target=server exit=0 duration_ms=111 stream=stdout\n"
                    "CPU: 11.0\n"
                    "MEM: 22.0\n"
                    "DISK: 33.0\n"
                    "RX_KBPS: 0\n"
                    "TX_KBPS: 0\n"
                    "SMTOKEN END\n"
                    "SMTOKEN BEGIN kind=gpu target=server exit=0 duration_ms=98 stream=stdout\n"
                    "0, NVIDIA A100, 70, 1024, 40960, 50\n"
                    "SMTOKEN END\n"
                )
            return _Result("", stderr="timeout", exit_code=-1, error="timeout")
        if "nvidia-smi" in remote_command:
            return _Result("0, NVIDIA A100, 70, 1024, 40960, 50")
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
                "ip_location=Los Angeles, California, United States (1.2.3.4)\n"
                "controller_port=7373"
            )
        return _Result("")


class _RetrySystemTimeoutExecutor:
    def __init__(self):
        self.calls = []
        self._system_calls = 0

    async def run(self, alias: str, remote_command: str, timeout_seconds: float | None = None):
        self.calls.append((alias, remote_command, timeout_seconds))
        if "CPU=$(top -bn1" in remote_command:
            self._system_calls += 1
            if self._system_calls == 1:
                return _Result("", stderr="timeout", exit_code=-1, error="timeout")
            return _Result("CPU: 11.0\nMEM: 22.0\nDISK: 33.0\nRX_KBPS: 0\nTX_KBPS: 0")
        return _Result("")


class _SystemParseFailureExecutor:
    def __init__(self):
        self.calls = []

    async def run(self, alias: str, remote_command: str, timeout_seconds: float | None = None):
        self.calls.append((alias, remote_command, timeout_seconds))
        if "CPU=$(top -bn1" in remote_command:
            return _Result("CPU: not-a-number\nMEM: 22.0\nDISK: 33.0\nRX_KBPS: 0\nTX_KBPS: 0")
        return _Result("")


class _AlwaysTimeoutClashSecretExecutor:
    def __init__(self):
        self.calls = []

    async def run(self, alias: str, remote_command: str, timeout_seconds: float | None = None):
        self.calls.append((alias, remote_command, timeout_seconds))
        if "clashsecret" in remote_command:
            return _Result("", stderr="timeout", exit_code=-1, error="timeout")
        return _Result("")


class _GitStatusCooldownExecutor:
    def __init__(self):
        self.calls = []
        self._git_status_calls = 0

    async def run(self, alias: str, remote_command: str, timeout_seconds: float | None = None):
        self.calls.append((alias, remote_command, timeout_seconds))
        if "git -C" in remote_command:
            self._git_status_calls += 1
            if self._git_status_calls == 1:
                return _Result("## main...origin/main\n M README.md\n")
            return _Result("", stderr="timeout", exit_code=-1, error="timeout")
        return _Result("")


class _RecoveredSystemRetryExecutor:
    def __init__(self):
        self.calls = []
        self._system_calls = 0

    async def run(self, alias: str, remote_command: str, timeout_seconds: float | None = None):
        self.calls.append((alias, remote_command, timeout_seconds))
        if "CPU=$(top -bn1" in remote_command:
            self._system_calls += 1
            if self._system_calls == 1:
                return _Result("", stderr="timeout", exit_code=-1, error="timeout")
            return _Result("CPU: 11.0\nMEM: 22.0\nDISK: 33.0\nRX_KBPS: 0\nTX_KBPS: 0")
        if "git -C" in remote_command:
            return _Result("## main...origin/main\n")
        if "clashsecret" in remote_command:
            return _Result("😼 当前密钥：mysecret")
        if "pgrep -f clash" in remote_command:
            return _Result("running=true\napi_reachable=true\nui_reachable=true\nmessage=ok")
        return _Result("")


class _MetricsBatchExecutor:
    def __init__(self):
        self.calls = []

    async def run(self, alias: str, remote_command: str, timeout_seconds: float | None = None):
        self.calls.append((alias, remote_command, timeout_seconds))
        return _Result(
            "SMTOKEN BEGIN kind=system target=server exit=0 duration_ms=111 stream=stdout\n"
            "CPU: 11.0\n"
            "MEM: 22.0\n"
            "DISK: 33.0\n"
            "RX_KBPS: 0\n"
            "TX_KBPS: 0\n"
            "SMTOKEN END\n"
            "SMTOKEN BEGIN kind=gpu target=server exit=0 duration_ms=98 stream=stdout\n"
            "0, NVIDIA A100, 70, 1024, 40960, 50\n"
            "SMTOKEN END\n"
        )


def _batch_stdout_section(*, kind: str, target: str, payload: str, exit_code: int = 0, duration_ms: int = 100) -> str:
    normalized_payload = payload if payload.endswith("\n") else f"{payload}\n"
    return (
        f"SMTOKEN BEGIN kind={kind} target={target} exit={exit_code} duration_ms={duration_ms} stream=stdout\n"
        f"{normalized_payload}"
        "SMTOKEN END\n"
    )


def _batch_stderr_section(*, kind: str, target: str, payload: str, exit_code: int = 1, duration_ms: int = 100) -> str:
    normalized_payload = payload if payload.endswith("\n") else f"{payload}\n"
    return (
        f"SMTOKEN BEGIN kind={kind} target={target} exit={exit_code} duration_ms={duration_ms} stream=stderr\n"
        f"{normalized_payload}"
        "SMTOKEN END\n"
    )


class _StatusBatchExecutor:
    def __init__(self):
        self.calls = []
        self._status_calls = 0

    async def run(self, alias: str, remote_command: str, timeout_seconds: float | None = None):
        self.calls.append((alias, remote_command, timeout_seconds))
        self._status_calls += 1
        if self._status_calls == 1:
            return _Result(
                _batch_stdout_section(
                    kind="git_status",
                    target="/work/repo-a",
                    payload="## main...origin/main\n M README.md\n",
                    duration_ms=120,
                )
                + _batch_stdout_section(
                    kind="git_status",
                    target="/work/repo-b",
                    payload="## main...origin/main\n",
                    duration_ms=110,
                )
                + _batch_stdout_section(
                    kind="clash_secret",
                    target="server",
                    payload="😼 当前密钥：mysecret\n",
                    duration_ms=90,
                )
                + _batch_stdout_section(
                    kind="clash_probe",
                    target="server",
                    payload="running=true\napi_reachable=true\nui_reachable=true\nmessage=ok\n",
                    duration_ms=95,
                )
            )
        return _Result(
            _batch_stdout_section(
                kind="git_status",
                target="/work/repo-a",
                payload="## main...origin/main\n M README.md\n",
                duration_ms=120,
            )
            + _batch_stdout_section(
                kind="git_status",
                target="/work/repo-b",
                payload="",
                exit_code=1,
                duration_ms=115,
            )
            + _batch_stderr_section(
                kind="git_status",
                target="/work/repo-b",
                payload="temporary git status failure\n",
                exit_code=1,
                duration_ms=115,
            )
            + _batch_stdout_section(
                kind="clash_secret",
                target="server",
                payload="😼 当前密钥：mysecret\n",
                duration_ms=90,
            )
            + _batch_stdout_section(
                kind="clash_probe",
                target="server",
                payload="running=true\napi_reachable=true\nui_reachable=true\nmessage=ok\n",
                duration_ms=95,
            )
        )


class _StatusBatchSecretFailureExecutor:
    def __init__(self):
        self.calls = []
        self._status_calls = 0

    async def run(self, alias: str, remote_command: str, timeout_seconds: float | None = None):
        self.calls.append((alias, remote_command, timeout_seconds))
        self._status_calls += 1
        if self._status_calls == 1:
            return _Result(
                _batch_stdout_section(
                    kind="git_status",
                    target="/work/repo-a",
                    payload="## main...origin/main\n",
                    duration_ms=120,
                )
                + _batch_stdout_section(
                    kind="clash_secret",
                    target="server",
                    payload="😼 当前密钥：mysecret\n",
                    duration_ms=90,
                )
                + _batch_stdout_section(
                    kind="clash_probe",
                    target="server",
                    payload="running=true\napi_reachable=true\nui_reachable=true\nmessage=ok\n",
                    duration_ms=95,
                )
            )
        return _Result(
            _batch_stdout_section(
                kind="git_status",
                target="/work/repo-a",
                payload="## main...origin/main\n",
                duration_ms=120,
            )
            + _batch_stdout_section(
                kind="clash_secret",
                target="server",
                payload="",
                exit_code=1,
                duration_ms=90,
            )
            + _batch_stderr_section(
                kind="clash_secret",
                target="server",
                payload="timeout\n",
                exit_code=1,
                duration_ms=90,
            )
        )


class _HealthyBatchTransport:
    def __init__(self):
        self.calls = []

    async def run(self, alias: str, remote_command: str, *, timeout_seconds: float):
        self.calls.append((alias, remote_command, timeout_seconds))
        return _Result(
            "SMTOKEN BEGIN kind=system target=server exit=0 duration_ms=111 stream=stdout\n"
            "CPU: 11.0\n"
            "MEM: 22.0\n"
            "DISK: 33.0\n"
            "RX_KBPS: 0\n"
            "TX_KBPS: 0\n"
            "SMTOKEN END\n"
            "SMTOKEN BEGIN kind=gpu target=server exit=0 duration_ms=98 stream=stdout\n"
            "0, NVIDIA A100, 70, 1024, 40960, 50\n"
            "SMTOKEN END\n"
        )


class _FailingThenHealthyBatchTransport:
    def __init__(self):
        self.calls = []
        self._call_count = 0

    async def run(self, alias: str, remote_command: str, *, timeout_seconds: float):
        self.calls.append((alias, remote_command, timeout_seconds))
        self._call_count += 1
        if self._call_count == 1:
            raise RuntimeError("persistent transport failed")
        return _Result(
            "SMTOKEN BEGIN kind=system target=server exit=0 duration_ms=111 stream=stdout\n"
            "CPU: 11.0\n"
            "MEM: 22.0\n"
            "DISK: 33.0\n"
            "RX_KBPS: 0\n"
            "TX_KBPS: 0\n"
            "SMTOKEN END\n"
            "SMTOKEN BEGIN kind=gpu target=server exit=0 duration_ms=98 stream=stdout\n"
            "0, NVIDIA A100, 70, 1024, 40960, 50\n"
            "SMTOKEN END\n"
        )


class _ConcurrencyTrackingRunner:
    def __init__(self, delay_seconds: float = 0.05):
        self.delay_seconds = delay_seconds
        self.calls = []
        self.active_calls = 0
        self.max_active_calls = 0

    async def run(self, argv: list[str]):
        self.calls.append(list(argv))
        self.active_calls += 1
        self.max_active_calls = max(self.max_active_calls, self.active_calls)
        try:
            await asyncio.sleep(self.delay_seconds)
            return _Result("ok")
        finally:
            self.active_calls -= 1


def test_ssh_command_executor_uses_dashboard_command_runner():
    from server_monitor.dashboard.command_runner import CommandRunner
    from server_monitor.dashboard.runtime import SshCommandExecutor

    executor = SshCommandExecutor()

    assert isinstance(executor.runner, CommandRunner)


@pytest.mark.asyncio
async def test_ssh_command_executor_serializes_commands_per_alias():
    from server_monitor.dashboard.runtime import SshCommandExecutor

    runner = _ConcurrencyTrackingRunner()
    executor = SshCommandExecutor(runner=runner)

    await asyncio.gather(
        executor.run("srv-shared", "echo first"),
        executor.run("srv-shared", "echo second"),
    )

    assert runner.max_active_calls == 1


@pytest.mark.asyncio
async def test_ssh_command_executor_allows_parallel_commands_for_different_aliases():
    from server_monitor.dashboard.runtime import SshCommandExecutor

    runner = _ConcurrencyTrackingRunner()
    executor = SshCommandExecutor(runner=runner)

    await asyncio.gather(
        executor.run("srv-a", "echo first"),
        executor.run("srv-b", "echo second"),
    )

    assert runner.max_active_calls == 2


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
async def test_runtime_batches_metrics_poll_per_server():
    from server_monitor.dashboard.runtime import DashboardRuntime
    from server_monitor.dashboard.ws_hub import WebSocketHub

    settings = DashboardSettings(
        metrics_interval_seconds=1.0,
        status_interval_seconds=10.0,
        servers=[
            ServerSettings(
                server_id="server-batched-metrics",
                ssh_alias="srv-batched-metrics",
                working_dirs=[],
                enabled_panels=["system", "gpu"],
            )
        ],
    )

    hub = WebSocketHub()
    ws = _FakeWebSocket()
    await hub.connect(ws)
    executor = _MetricsBatchExecutor()
    runtime = DashboardRuntime(
        hub=hub,
        settings_store=_FakeSettingsStore(settings),
        executor=executor,
    )

    await runtime.poll_once()

    payload = ws.messages[0]
    assert len(executor.calls) == 1
    assert payload["snapshot"]["cpu_percent"] == 11.0
    assert payload["snapshot"]["gpus"][0]["name"] == "NVIDIA A100"
    assert payload["command_health"]["system"]["state"] == "healthy"
    assert payload["command_health"]["gpu"]["state"] == "healthy"


@pytest.mark.asyncio
async def test_runtime_batches_status_poll_and_keeps_cached_repo_on_single_repo_failure():
    from server_monitor.dashboard.runtime import DashboardRuntime
    from server_monitor.dashboard.ws_hub import WebSocketHub

    settings = DashboardSettings(
        metrics_interval_seconds=1.0,
        status_interval_seconds=0.0,
        servers=[
            ServerSettings(
                server_id="server-batched-status",
                ssh_alias="srv-batched-status",
                working_dirs=["/work/repo-a", "/work/repo-b"],
                enabled_panels=["git", "clash"],
            )
        ],
    )

    hub = WebSocketHub()
    ws = _FakeWebSocket()
    await hub.connect(ws)
    executor = _StatusBatchExecutor()
    runtime = DashboardRuntime(
        hub=hub,
        settings_store=_FakeSettingsStore(settings),
        executor=executor,
    )

    await runtime.poll_once()
    await runtime.poll_once()

    payload = ws.messages[-1]
    assert len(executor.calls) == 2
    assert len(payload["repos"]) == 2
    assert {repo["path"] for repo in payload["repos"]} == {"/work/repo-a", "/work/repo-b"}
    assert payload["command_health"]["git"]["state"] == "failed"


@pytest.mark.asyncio
async def test_runtime_prefers_batch_transport_for_metrics_when_available():
    from server_monitor.dashboard.runtime import DashboardRuntime
    from server_monitor.dashboard.ws_hub import WebSocketHub

    settings = DashboardSettings(
        metrics_interval_seconds=1.0,
        status_interval_seconds=10.0,
        servers=[
            ServerSettings(
                server_id="server-persistent-metrics",
                ssh_alias="srv-persistent-metrics",
                working_dirs=[],
                enabled_panels=["system", "gpu"],
            )
        ],
    )

    hub = WebSocketHub()
    ws = _FakeWebSocket()
    await hub.connect(ws)
    batch_transport = _HealthyBatchTransport()
    executor = _MetricsBatchExecutor()
    runtime = DashboardRuntime(
        hub=hub,
        settings_store=_FakeSettingsStore(settings),
        executor=executor,
        batch_transport=batch_transport,
    )

    await runtime.poll_once()

    payload = ws.messages[0]
    assert len(batch_transport.calls) == 1
    assert executor.calls == []
    assert payload["snapshot"]["cpu_percent"] == 11.0


@pytest.mark.asyncio
async def test_runtime_falls_back_to_one_shot_executor_when_batch_transport_fails():
    from server_monitor.dashboard.runtime import DashboardRuntime
    from server_monitor.dashboard.ws_hub import WebSocketHub

    settings = DashboardSettings(
        metrics_interval_seconds=1.0,
        status_interval_seconds=10.0,
        servers=[
            ServerSettings(
                server_id="server-batch-fallback",
                ssh_alias="srv-batch-fallback",
                working_dirs=[],
                enabled_panels=["system", "gpu"],
            )
        ],
    )

    hub = WebSocketHub()
    ws = _FakeWebSocket()
    await hub.connect(ws)
    batch_transport = _FailingThenHealthyBatchTransport()
    executor = _MetricsBatchExecutor()
    runtime = DashboardRuntime(
        hub=hub,
        settings_store=_FakeSettingsStore(settings),
        executor=executor,
        batch_transport=batch_transport,
    )

    await runtime.poll_once()

    payload = ws.messages[0]
    assert len(batch_transport.calls) == 1
    assert len(executor.calls) == 1
    assert payload["snapshot"]["cpu_percent"] == 11.0


@pytest.mark.asyncio
async def test_runtime_retries_batch_transport_on_later_polls_after_fallback():
    from server_monitor.dashboard.runtime import DashboardRuntime
    from server_monitor.dashboard.ws_hub import WebSocketHub

    settings = DashboardSettings(
        metrics_interval_seconds=1.0,
        status_interval_seconds=10.0,
        servers=[
            ServerSettings(
                server_id="server-batch-recover",
                ssh_alias="srv-batch-recover",
                working_dirs=[],
                enabled_panels=["system", "gpu"],
            )
        ],
    )

    hub = WebSocketHub()
    ws = _FakeWebSocket()
    await hub.connect(ws)
    batch_transport = _FailingThenHealthyBatchTransport()
    executor = _MetricsBatchExecutor()
    runtime = DashboardRuntime(
        hub=hub,
        settings_store=_FakeSettingsStore(settings),
        executor=executor,
        batch_transport=batch_transport,
    )

    await runtime.poll_once()
    await runtime.poll_once()

    assert len(batch_transport.calls) == 2
    assert len(executor.calls) == 1
    assert ws.messages[-1]["snapshot"]["cpu_percent"] == 11.0


@pytest.mark.asyncio
async def test_runtime_keeps_cached_clash_snapshot_when_batched_secret_check_fails():
    from server_monitor.dashboard.runtime import DashboardRuntime
    from server_monitor.dashboard.ws_hub import WebSocketHub

    settings = DashboardSettings(
        metrics_interval_seconds=1.0,
        status_interval_seconds=0.0,
        servers=[
            ServerSettings(
                server_id="server-batched-clash",
                ssh_alias="srv-batched-clash",
                working_dirs=["/work/repo-a"],
                enabled_panels=["git", "clash"],
            )
        ],
    )

    hub = WebSocketHub()
    ws = _FakeWebSocket()
    await hub.connect(ws)
    executor = _StatusBatchSecretFailureExecutor()
    runtime = DashboardRuntime(
        hub=hub,
        settings_store=_FakeSettingsStore(settings),
        executor=executor,
    )

    await runtime.poll_once()
    await runtime.poll_once()

    payload = ws.messages[-1]
    assert len(executor.calls) == 2
    assert payload["clash"]["running"] is True
    assert payload["clash"]["message"] == "ok"


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
    executor = _HostUnreachableExecutor()

    runtime = DashboardRuntime(
        hub=hub,
        settings_store=_FakeSettingsStore(settings),
        executor=executor,
    )

    await runtime.poll_once()

    assert len(executor.calls) <= 4
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
@pytest.mark.parametrize(
    ("operation", "branch", "expected_snippet"),
    [
        ("fetch", None, "fetch --prune --tags"),
        ("pull", None, "pull --ff-only"),
        ("checkout", "main", "checkout 'main'"),
    ],
)
async def test_runtime_git_ops_prefer_batch_transport_when_available(operation: str, branch: str | None, expected_snippet: str):
    from server_monitor.dashboard.runtime import DashboardRuntime
    from server_monitor.dashboard.ws_hub import WebSocketHub

    settings = DashboardSettings(
        servers=[
            ServerSettings(
                server_id="server-batch",
                ssh_alias="srv-batch",
                working_dirs=["/work/repo-batch"],
                enabled_panels=["git"],
            )
        ]
    )
    executor = _TimeoutAwareGitExecutor()
    batch_transport = _GitOpBatchTransport()
    runtime = DashboardRuntime(
        hub=WebSocketHub(),
        settings_store=_FakeSettingsStore(settings),
        executor=executor,
        batch_transport=batch_transport,
    )

    result = await runtime.run_git_operation(
        server_id="server-batch",
        repo_path="/work/repo-batch",
        operation=operation,
        branch=branch,
    )

    assert result["ok"] is True
    assert any(expected_snippet in call[1] for call in batch_transport.calls)
    assert any("status --porcelain --branch" in call[1] for call in batch_transport.calls)
    assert executor.calls == []
    assert result["repo"]["behind"] == 2


@pytest.mark.asyncio
async def test_runtime_git_op_does_not_replay_mutating_command_when_batch_transport_fails():
    from server_monitor.dashboard.runtime import DashboardRuntime
    from server_monitor.dashboard.ws_hub import WebSocketHub

    settings = DashboardSettings(
        servers=[
            ServerSettings(
                server_id="server-batch-fallback",
                ssh_alias="srv-batch-fallback",
                working_dirs=["/work/repo-batch-fallback"],
                enabled_panels=["git"],
            )
        ]
    )
    executor = _GitOpExecutor()
    batch_transport = _FailingGitOpBatchTransport()
    runtime = DashboardRuntime(
        hub=WebSocketHub(),
        settings_store=_FakeSettingsStore(settings),
        executor=executor,
        batch_transport=batch_transport,
    )

    result = await runtime.run_git_operation(
        server_id="server-batch-fallback",
        repo_path="/work/repo-batch-fallback",
        operation="fetch",
    )

    assert result["ok"] is False
    assert len(batch_transport.calls) == 2
    assert len(executor.calls) == 1
    assert all("fetch --prune --tags" not in call[1] for call in executor.calls)
    assert any("status --porcelain --branch" in call[1] for call in executor.calls)
    assert result["stderr"] == "persistent transport failed"
    assert result["repo"]["path"] == "/work/repo-batch-fallback"


@pytest.mark.asyncio
async def test_runtime_git_status_poll_uses_extended_timeout():
    from server_monitor.dashboard.runtime import DashboardRuntime
    from server_monitor.dashboard.ws_hub import WebSocketHub

    settings = DashboardSettings(
        metrics_interval_seconds=1.0,
        status_interval_seconds=0.0,
        servers=[
            ServerSettings(
                server_id="server-git-timeout",
                ssh_alias="srv-git-timeout",
                working_dirs=["/work/repo-timeout"],
                enabled_panels=["git"],
            )
        ],
    )

    hub = WebSocketHub()
    ws = _FakeWebSocket()
    await hub.connect(ws)
    executor = _SlowGitStatusExecutor()
    runtime = DashboardRuntime(
        hub=hub,
        settings_store=_FakeSettingsStore(settings),
        executor=executor,
    )

    await runtime.poll_once()

    payload = ws.messages[0]
    assert payload["repos"][0]["path"] == "/work/repo-timeout"
    assert payload["command_health"]["git"]["state"] == "healthy"
    git_calls = [call for call in executor.calls if "status --porcelain --branch" in call[1]]
    assert len(git_calls) == 1
    assert git_calls[0][2] is not None
    assert git_calls[0][2] >= 5.0


@pytest.mark.asyncio
async def test_runtime_git_status_poll_prefers_one_long_attempt_over_short_retries():
    from server_monitor.dashboard.runtime import DashboardRuntime
    from server_monitor.dashboard.ws_hub import WebSocketHub

    settings = DashboardSettings(
        metrics_interval_seconds=1.0,
        status_interval_seconds=0.0,
        servers=[
            ServerSettings(
                server_id="server-git-slow",
                ssh_alias="srv-git-slow",
                working_dirs=["/work/repo-slow"],
                enabled_panels=["git"],
            )
        ],
    )

    hub = WebSocketHub()
    ws = _FakeWebSocket()
    await hub.connect(ws)
    executor = _VerySlowGitStatusExecutor()
    runtime = DashboardRuntime(
        hub=hub,
        settings_store=_FakeSettingsStore(settings),
        executor=executor,
    )

    await runtime.poll_once()

    payload = ws.messages[0]
    assert payload["repos"][0]["path"] == "/work/repo-slow"
    assert payload["command_health"]["git"]["state"] == "healthy"
    git_calls = [call for call in executor.calls if "status --porcelain --branch" in call[1]]
    assert len(git_calls) == 1
    assert git_calls[0][2] is not None
    assert git_calls[0][2] >= 10.0


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


@pytest.mark.asyncio
async def test_runtime_retries_system_timeout_once_before_success():
    from server_monitor.dashboard.runtime import DashboardRuntime
    from server_monitor.dashboard.ws_hub import WebSocketHub

    settings = DashboardSettings(
        metrics_interval_seconds=1.0,
        status_interval_seconds=10.0,
        servers=[
            ServerSettings(
                server_id="server-system-retry",
                ssh_alias="srv-system-retry",
                working_dirs=[],
                enabled_panels=["system"],
            )
        ],
    )

    hub = WebSocketHub()
    ws = _FakeWebSocket()
    await hub.connect(ws)
    executor = _RetrySystemTimeoutExecutor()
    runtime = DashboardRuntime(
        hub=hub,
        settings_store=_FakeSettingsStore(settings),
        executor=executor,
    )

    await runtime.poll_once()

    payload = ws.messages[0]
    health = runtime.get_recent_command_health(
        server_id="server-system-retry",
        command_kind="system",
        target_label="server",
    )[0]
    assert payload["snapshot"]["cpu_percent"] == 11.0
    assert health["attempt_count"] == 2
    assert health["failure_class"] == "ok"


@pytest.mark.asyncio
async def test_runtime_does_not_retry_parse_failure():
    from server_monitor.dashboard.runtime import DashboardRuntime
    from server_monitor.dashboard.ws_hub import WebSocketHub

    settings = DashboardSettings(
        metrics_interval_seconds=1.0,
        status_interval_seconds=10.0,
        servers=[
            ServerSettings(
                server_id="server-system-parse",
                ssh_alias="srv-system-parse",
                working_dirs=[],
                enabled_panels=["system"],
            )
        ],
    )

    hub = WebSocketHub()
    ws = _FakeWebSocket()
    await hub.connect(ws)
    executor = _SystemParseFailureExecutor()
    runtime = DashboardRuntime(
        hub=hub,
        settings_store=_FakeSettingsStore(settings),
        executor=executor,
    )

    await runtime.poll_once()

    payload = ws.messages[0]
    health = runtime.get_recent_command_health(
        server_id="server-system-parse",
        command_kind="system",
        target_label="server",
    )[0]
    assert payload["snapshot"]["metadata"]["metrics_error"].startswith("system parse failed:")
    assert health["attempt_count"] == 1
    assert health["failure_class"] == "parse_error"


@pytest.mark.asyncio
async def test_runtime_applies_cooldown_after_repeated_clash_secret_failures():
    from server_monitor.dashboard.command_policy import CommandKind, CommandPolicy
    from server_monitor.dashboard.runtime import DashboardRuntime
    from server_monitor.dashboard.ws_hub import WebSocketHub

    settings = DashboardSettings(
        metrics_interval_seconds=1.0,
        status_interval_seconds=0.0,
        servers=[
            ServerSettings(
                server_id="server-clash-cooldown",
                ssh_alias="srv-clash-cooldown",
                working_dirs=[],
                enabled_panels=["clash"],
            )
        ],
    )

    hub = WebSocketHub()
    ws = _FakeWebSocket()
    await hub.connect(ws)
    executor = _AlwaysTimeoutClashSecretExecutor()
    runtime = DashboardRuntime(
        hub=hub,
        settings_store=_FakeSettingsStore(settings),
        executor=executor,
    )
    runtime._command_policies[CommandKind.CLASH_SECRET] = CommandPolicy(
        timeout_seconds=3.0,
        max_attempts=1,
        base_backoff_seconds=0.0,
        retry_on_timeout=True,
        retry_on_ssh_error=True,
        retry_on_nonzero_exit=False,
        cooldown_after_failures=2,
        cooldown_seconds=60.0,
    )

    await runtime.poll_once()
    await runtime.poll_once()
    await runtime.poll_once()

    health = runtime.get_recent_command_health(
        server_id="server-clash-cooldown",
        command_kind="clash_secret",
        target_label="server",
    )
    assert health[-1]["failure_class"] == "cooldown_skip"


@pytest.mark.asyncio
async def test_runtime_keeps_cached_git_repo_during_cooldown():
    from server_monitor.dashboard.command_policy import CommandKind, CommandPolicy
    from server_monitor.dashboard.runtime import DashboardRuntime
    from server_monitor.dashboard.ws_hub import WebSocketHub

    settings = DashboardSettings(
        metrics_interval_seconds=1.0,
        status_interval_seconds=0.0,
        servers=[
            ServerSettings(
                server_id="server-git-cooldown",
                ssh_alias="srv-git-cooldown",
                working_dirs=["/work/repo-a"],
                enabled_panels=["git"],
            )
        ],
    )

    hub = WebSocketHub()
    ws = _FakeWebSocket()
    await hub.connect(ws)
    executor = _GitStatusCooldownExecutor()
    runtime = DashboardRuntime(
        hub=hub,
        settings_store=_FakeSettingsStore(settings),
        executor=executor,
    )
    runtime._command_policies[CommandKind.GIT_STATUS] = CommandPolicy(
        timeout_seconds=3.0,
        max_attempts=1,
        base_backoff_seconds=0.0,
        retry_on_timeout=True,
        retry_on_ssh_error=True,
        retry_on_nonzero_exit=False,
        cooldown_after_failures=1,
        cooldown_seconds=60.0,
    )

    await runtime.poll_once()
    await runtime.poll_once()
    await runtime.poll_once()

    payload = ws.messages[-1]
    health = runtime.get_recent_command_health(
        server_id="server-git-cooldown",
        command_kind="git_status",
        target_label="/work/repo-a",
    )
    assert payload["repos"][0]["path"] == "/work/repo-a"
    assert health[-1]["failure_class"] == "cooldown_skip"


@pytest.mark.asyncio
async def test_runtime_runs_status_poll_when_system_retry_recovers():
    from server_monitor.dashboard.runtime import DashboardRuntime
    from server_monitor.dashboard.ws_hub import WebSocketHub

    settings = DashboardSettings(
        metrics_interval_seconds=1.0,
        status_interval_seconds=0.0,
        servers=[
            ServerSettings(
                server_id="server-recovered-status",
                ssh_alias="srv-recovered-status",
                working_dirs=["/work/repo-a"],
                enabled_panels=["system", "git", "clash"],
            )
        ],
    )

    hub = WebSocketHub()
    ws = _FakeWebSocket()
    await hub.connect(ws)
    executor = _RecoveredSystemRetryExecutor()
    runtime = DashboardRuntime(
        hub=hub,
        settings_store=_FakeSettingsStore(settings),
        executor=executor,
    )

    await runtime.poll_once()

    payload = ws.messages[0]
    assert payload["snapshot"]["metadata"].get("ssh_error") is None
    assert any("clashsecret" in call[1] for call in executor.calls)
    assert any("git -C" in call[1] for call in executor.calls)


@pytest.mark.asyncio
async def test_runtime_emits_command_health_latency_for_healthy_system():
    from server_monitor.dashboard.runtime import DashboardRuntime
    from server_monitor.dashboard.ws_hub import WebSocketHub

    settings = DashboardSettings(
        metrics_interval_seconds=1.0,
        status_interval_seconds=10.0,
        servers=[
            ServerSettings(
                server_id="server-health-system",
                ssh_alias="srv-health-system",
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
        executor=_FakeExecutor(),
    )

    await runtime.poll_once()

    payload = ws.messages[0]
    assert payload["command_health"]["system"]["state"] == "healthy"
    assert payload["command_health"]["system"]["label"].endswith("ms")
    assert payload["command_health"]["system"]["updated_at"]


@pytest.mark.asyncio
async def test_runtime_emits_retrying_state_for_successful_retry():
    from server_monitor.dashboard.runtime import DashboardRuntime
    from server_monitor.dashboard.ws_hub import WebSocketHub

    settings = DashboardSettings(
        metrics_interval_seconds=1.0,
        status_interval_seconds=10.0,
        servers=[
            ServerSettings(
                server_id="server-health-retry",
                ssh_alias="srv-health-retry",
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
        executor=_RetrySystemTimeoutExecutor(),
    )

    await runtime.poll_once()

    payload = ws.messages[0]
    assert payload["command_health"]["system"]["state"] == "retrying"
    assert payload["command_health"]["system"]["label"] == "retry x2"


@pytest.mark.asyncio
async def test_runtime_emits_failed_state_for_parse_failure():
    from server_monitor.dashboard.runtime import DashboardRuntime
    from server_monitor.dashboard.ws_hub import WebSocketHub

    settings = DashboardSettings(
        metrics_interval_seconds=1.0,
        status_interval_seconds=10.0,
        servers=[
            ServerSettings(
                server_id="server-health-failed",
                ssh_alias="srv-health-failed",
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
        executor=_SystemParseFailureExecutor(),
    )

    await runtime.poll_once()

    payload = ws.messages[0]
    assert payload["command_health"]["system"]["state"] == "failed"
    assert payload["command_health"]["system"]["label"] == "failed"


@pytest.mark.asyncio
async def test_runtime_emits_unknown_git_health_when_status_poll_never_runs():
    from server_monitor.dashboard.runtime import DashboardRuntime
    from server_monitor.dashboard.ws_hub import WebSocketHub

    settings = DashboardSettings(
        metrics_interval_seconds=1.0,
        status_interval_seconds=0.0,
        servers=[
            ServerSettings(
                server_id="server-health-unknown",
                ssh_alias="srv-health-unknown",
                working_dirs=["/work/repo-a"],
                enabled_panels=["system", "git"],
            )
        ],
    )

    hub = WebSocketHub()
    ws = _FakeWebSocket()
    await hub.connect(ws)
    runtime = DashboardRuntime(
        hub=hub,
        settings_store=_FakeSettingsStore(settings),
        executor=_HostUnreachableExecutor(),
    )

    await runtime.poll_once()

    payload = ws.messages[0]
    assert payload["command_health"]["git"]["state"] == "unknown"
    assert payload["command_health"]["git"]["label"] == "--"


@pytest.mark.asyncio
async def test_runtime_emits_cooldown_state_for_clash_after_cooldown_skip():
    from server_monitor.dashboard.command_policy import CommandKind, CommandPolicy
    from server_monitor.dashboard.runtime import DashboardRuntime
    from server_monitor.dashboard.ws_hub import WebSocketHub

    settings = DashboardSettings(
        metrics_interval_seconds=1.0,
        status_interval_seconds=0.0,
        servers=[
            ServerSettings(
                server_id="server-health-cooldown",
                ssh_alias="srv-health-cooldown",
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
        executor=_AlwaysTimeoutClashSecretExecutor(),
    )
    runtime._command_policies[CommandKind.CLASH_SECRET] = CommandPolicy(
        timeout_seconds=3.0,
        max_attempts=1,
        base_backoff_seconds=0.0,
        retry_on_timeout=True,
        retry_on_ssh_error=True,
        retry_on_nonzero_exit=False,
        cooldown_after_failures=2,
        cooldown_seconds=60.0,
    )

    await runtime.poll_once()
    await runtime.poll_once()
    await runtime.poll_once()

    payload = ws.messages[-1]
    assert payload["command_health"]["clash"]["state"] == "cooldown"
    assert payload["command_health"]["clash"]["label"] == "cooldown"


@pytest.mark.asyncio
async def test_runtime_git_health_uses_worst_repo_state():
    from server_monitor.dashboard.runtime import DashboardRuntime
    from server_monitor.dashboard.ws_hub import WebSocketHub

    settings = DashboardSettings(
        metrics_interval_seconds=1.0,
        status_interval_seconds=0.0,
        servers=[
            ServerSettings(
                server_id="server-health-git",
                ssh_alias="srv-health-git",
                working_dirs=["/work/repo-ok", "/work/repo-fail"],
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
        executor=_MixedRepoFreshnessExecutor(),
    )

    await runtime.poll_once()
    await runtime.poll_once()

    payload = ws.messages[-1]
    assert payload["command_health"]["git"]["state"] == "failed"
    assert payload["command_health"]["git"]["label"] == "failed"


@pytest.mark.asyncio
async def test_runtime_clash_health_prefers_secret_failure_over_old_probe_success():
    from server_monitor.dashboard.command_policy import CommandKind, CommandPolicy
    from server_monitor.dashboard.runtime import DashboardRuntime
    from server_monitor.dashboard.ws_hub import WebSocketHub

    settings = DashboardSettings(
        metrics_interval_seconds=1.0,
        status_interval_seconds=0.0,
        servers=[
            ServerSettings(
                server_id="server-health-clash",
                ssh_alias="srv-health-clash",
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
    runtime._command_policies[CommandKind.CLASH_SECRET] = CommandPolicy(
        timeout_seconds=3.0,
        max_attempts=1,
        base_backoff_seconds=0.0,
        retry_on_timeout=True,
        retry_on_ssh_error=True,
        retry_on_nonzero_exit=False,
        cooldown_after_failures=3,
        cooldown_seconds=60.0,
    )

    await runtime.poll_once()
    first_task = runtime._status_poll_tasks.get("server-health-clash")
    if first_task is not None:
        await first_task
        runtime._consume_finished_status_poll_task("server-health-clash")
    await runtime.poll_once()

    payload = ws.messages[-1]
    assert payload["command_health"]["clash"]["state"] == "failed"
    assert payload["command_health"]["clash"]["label"] == "failed"


def test_metrics_sleep_seconds_compensates_poll_time():
    from server_monitor.dashboard.runtime import _metrics_sleep_seconds

    assert _metrics_sleep_seconds(interval_seconds=1.0, elapsed_seconds=0.25) == pytest.approx(0.75)
    assert _metrics_sleep_seconds(interval_seconds=1.0, elapsed_seconds=1.6) == pytest.approx(0.05)


def test_batched_clash_secret_command_runs_lookup_in_child_shell():
    from server_monitor.dashboard.runtime import _batched_clash_secret_command

    command = _batched_clash_secret_command()

    assert "sh -lc" in command


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
    assert "controller_port=" in cmd


def test_clash_command_routes_ip_lookup_via_detected_proxy_port():
    from server_monitor.dashboard.runtime import _clash_command

    cmd = _clash_command(
        api_probe_url="http://127.0.0.1:9090/version",
        ui_probe_url="http://127.0.0.1:9090/ui",
        secret="mysecret",
    )

    assert "mixed-port:" in cmd
    assert "PROXY_URL=" in cmd
    assert '--proxy "$PROXY_URL"' in cmd


def test_clash_command_parses_ip_lookup_fields_in_provider_order():
    from server_monitor.dashboard.runtime import _clash_command

    cmd = _clash_command(
        api_probe_url="http://127.0.0.1:9090/version",
        ui_probe_url="http://127.0.0.1:9090/ui",
        secret="mysecret",
    )

    assert "IP_COUNTRY=$(printf '%s\\n' \"$IP_INFO\" | sed -n '1p'" in cmd
    assert "IP_REGION=$(printf '%s\\n' \"$IP_INFO\" | sed -n '2p'" in cmd
    assert "IP_CITY=$(printf '%s\\n' \"$IP_INFO\" | sed -n '3p'" in cmd
    assert "IP_ADDR=$(printf '%s\\n' \"$IP_INFO\" | sed -n '4p'" in cmd


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
    assert payload["clash"]["controller_port"] == "7373"
    assert payload["clash"]["message"] == "ok"
    await runtime.stop()


@pytest.mark.asyncio
async def test_runtime_metrics_stream_start_binds_and_starts_manager():
    from server_monitor.dashboard.runtime import DashboardRuntime
    from server_monitor.dashboard.ws_hub import WebSocketHub

    settings = DashboardSettings(
        metrics_interval_seconds=1.0,
        status_interval_seconds=10.0,
        servers=[
            ServerSettings(
                server_id="server-stream-start",
                ssh_alias="srv-stream-start",
                working_dirs=["/work/repo-a"],
                enabled_panels=["system", "gpu", "git"],
            )
        ],
    )

    metrics_stream_manager = _FakeMetricsStreamManager()
    runtime = DashboardRuntime(
        hub=WebSocketHub(),
        settings_store=_FakeSettingsStore(settings),
        executor=_FakeExecutor(),
        metrics_stream_manager=metrics_stream_manager,
    )

    await runtime.start()
    await runtime.stop()

    assert len(metrics_stream_manager.started_with) == 1
    assert metrics_stream_manager.started_with[0][0].server_id == "server-stream-start"
    assert metrics_stream_manager.stopped is True


@pytest.mark.asyncio
async def test_runtime_metrics_stream_poll_once_syncs_servers_after_settings_change():
    from server_monitor.dashboard.runtime import DashboardRuntime
    from server_monitor.dashboard.ws_hub import WebSocketHub

    settings = DashboardSettings(
        metrics_interval_seconds=3600.0,
        status_interval_seconds=3600.0,
        servers=[],
    )
    settings_store = _FakeSettingsStore(settings)
    metrics_stream_manager = _FakeSyncingMetricsStreamManager()
    runtime = DashboardRuntime(
        hub=WebSocketHub(),
        settings_store=settings_store,
        executor=_FakeExecutor(),
        metrics_stream_manager=metrics_stream_manager,
    )

    await runtime.start()
    settings_store._settings.servers.append(
        ServerSettings(
            server_id="server-stream-added",
            ssh_alias="srv-stream-added",
            working_dirs=[],
            enabled_panels=["system", "gpu"],
        )
    )
    await runtime.poll_once()
    await runtime.stop()

    assert metrics_stream_manager.sync_calls
    assert metrics_stream_manager.sync_calls[-1][0].server_id == "server-stream-added"


@pytest.mark.asyncio
async def test_runtime_metrics_stream_sample_updates_snapshot_and_broadcasts_immediately():
    from server_monitor.dashboard.metrics_stream_protocol import MetricsStreamSample
    from server_monitor.dashboard.runtime import DashboardRuntime
    from server_monitor.dashboard.ws_hub import WebSocketHub

    settings = DashboardSettings(
        metrics_interval_seconds=1.0,
        status_interval_seconds=10.0,
        servers=[
            ServerSettings(
                server_id="server-stream-sample",
                ssh_alias="srv-stream-sample",
                working_dirs=[],
                enabled_panels=["system", "gpu"],
            )
        ],
    )

    hub = WebSocketHub()
    ws = _FakeWebSocket()
    await hub.connect(ws)
    metrics_stream_manager = _FakeMetricsStreamManager()
    runtime = DashboardRuntime(
        hub=hub,
        settings_store=_FakeSettingsStore(settings),
        executor=_FakeExecutor(),
        metrics_stream_manager=metrics_stream_manager,
    )

    await runtime.start()
    await metrics_stream_manager.emit_state("server-stream-sample", "live")
    await metrics_stream_manager.emit_sample(
        "server-stream-sample",
        MetricsStreamSample(
            sequence=1,
            server_time="2026-03-12T12:00:00+00:00",
            sample_interval_ms=250,
            cpu_percent=11.0,
            memory_percent=22.0,
            disk_percent=33.0,
            network_rx_kbps=44.0,
            network_tx_kbps=55.0,
            gpus=[
                {
                    "index": 0,
                    "name": "NVIDIA A100",
                    "utilization_gpu_percent": 70.0,
                    "memory_used_mib": 1024,
                    "memory_total_mib": 40960,
                    "temperature_celsius": 50.0,
                }
            ],
        ),
    )
    await runtime.stop()

    payload = ws.messages[-1]
    assert payload["snapshot"]["cpu_percent"] == 11.0
    assert payload["snapshot"]["network_rx_kbps"] == 44.0
    assert payload["snapshot"]["gpus"][0]["name"] == "NVIDIA A100"
    assert payload["freshness"]["system"]["state"] == "live"
    assert payload["freshness"]["gpu"]["state"] == "live"
    assert payload["metrics_stream"]["state"] == "live"
    assert payload["metrics_stream"]["sample_interval_ms"] == 250


@pytest.mark.asyncio
async def test_runtime_metrics_stream_poll_once_only_runs_git_and_clash_status():
    from server_monitor.dashboard.runtime import DashboardRuntime
    from server_monitor.dashboard.ws_hub import WebSocketHub

    settings = DashboardSettings(
        metrics_interval_seconds=1.0,
        status_interval_seconds=0.0,
        servers=[
            ServerSettings(
                server_id="server-stream-status-only",
                ssh_alias="srv-stream-status-only",
                working_dirs=["/work/repo-a"],
                enabled_panels=["system", "gpu", "git", "clash"],
            )
        ],
    )

    executor = _FakeExecutor()
    runtime = DashboardRuntime(
        hub=WebSocketHub(),
        settings_store=_FakeSettingsStore(settings),
        executor=executor,
        metrics_stream_manager=_FakeMetricsStreamManager(),
    )

    await runtime.poll_once()
    await asyncio.sleep(0.01)
    await runtime.stop()

    assert executor.calls
    assert not any("SMTOKEN BEGIN kind=system target=server" in call[1] for call in executor.calls)
    assert any("SMTOKEN BEGIN kind=git_status target=" in call[1] for call in executor.calls)


@pytest.mark.asyncio
async def test_runtime_metrics_stream_health_reports_transport_latency():
    from server_monitor.dashboard.metrics_stream_protocol import MetricsStreamSample
    from server_monitor.dashboard.runtime import DashboardRuntime
    from server_monitor.dashboard.ws_hub import WebSocketHub

    settings = DashboardSettings(
        metrics_interval_seconds=1.0,
        status_interval_seconds=10.0,
        servers=[
            ServerSettings(
                server_id="server-stream-health",
                ssh_alias="srv-stream-health",
                working_dirs=[],
                enabled_panels=["system", "gpu"],
            )
        ],
    )

    hub = WebSocketHub()
    ws = _FakeWebSocket()
    await hub.connect(ws)
    metrics_stream_manager = _FakeMetricsStreamManager()
    runtime = DashboardRuntime(
        hub=hub,
        settings_store=_FakeSettingsStore(settings),
        executor=_FakeExecutor(),
        metrics_stream_manager=metrics_stream_manager,
    )

    await runtime.start()
    await metrics_stream_manager.emit_state("server-stream-health", "live")
    sample_server_time = datetime.now(UTC).isoformat()
    await metrics_stream_manager.emit_sample(
        "server-stream-health",
        MetricsStreamSample(
            sequence=1,
            server_time=sample_server_time,
            sample_interval_ms=250,
            cpu_percent=11.0,
            memory_percent=22.0,
            disk_percent=33.0,
            network_rx_kbps=44.0,
            network_tx_kbps=55.0,
            gpus=[],
        ),
    )
    await runtime.stop()

    payload = ws.messages[-1]
    assert payload["command_health"]["system"]["state"] == "healthy"
    assert payload["command_health"]["system"]["latency_ms"] is not None
    assert payload["command_health"]["system"]["latency_ms"] >= 0
    assert payload["command_health"]["system"]["label"] == f'{payload["command_health"]["system"]["latency_ms"]}ms'
    assert payload["command_health"]["gpu"]["state"] == "healthy"
    assert payload["command_health"]["gpu"]["latency_ms"] is not None
    assert payload["command_health"]["gpu"]["latency_ms"] >= 0
    assert payload["command_health"]["gpu"]["label"] == f'{payload["command_health"]["gpu"]["latency_ms"]}ms'


@pytest.mark.asyncio
async def test_runtime_metrics_stream_cached_disconnect_keeps_last_sample_visible():
    from server_monitor.dashboard.metrics_stream_protocol import MetricsStreamSample
    from server_monitor.dashboard.runtime import DashboardRuntime
    from server_monitor.dashboard.ws_hub import WebSocketHub

    settings = DashboardSettings(
        metrics_interval_seconds=1.0,
        status_interval_seconds=10.0,
        servers=[
            ServerSettings(
                server_id="server-stream-cached",
                ssh_alias="srv-stream-cached",
                working_dirs=[],
                enabled_panels=["system", "gpu"],
            )
        ],
    )

    hub = WebSocketHub()
    ws = _FakeWebSocket()
    await hub.connect(ws)
    metrics_stream_manager = _FakeMetricsStreamManager()
    runtime = DashboardRuntime(
        hub=hub,
        settings_store=_FakeSettingsStore(settings),
        executor=_FakeExecutor(),
        metrics_stream_manager=metrics_stream_manager,
    )

    await runtime.start()
    await metrics_stream_manager.emit_state("server-stream-cached", "live")
    await metrics_stream_manager.emit_sample(
        "server-stream-cached",
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
    stale_timestamp = (datetime.now(UTC) - timedelta(seconds=5)).isoformat()
    runtime._system_last_updated_at["server-stream-cached"] = stale_timestamp
    runtime._gpu_last_updated_at["server-stream-cached"] = stale_timestamp
    await metrics_stream_manager.emit_state("server-stream-cached", "reconnecting")

    await runtime.poll_once()
    await runtime.stop()

    payload = ws.messages[-1]
    assert payload["snapshot"]["cpu_percent"] == 11.0
    assert payload["snapshot"]["memory_percent"] == 22.0
    assert payload["freshness"]["system"]["state"] == "cached"
    assert payload["freshness"]["gpu"]["state"] == "cached"
    assert payload["command_health"]["system"]["state"] == "retrying"
    assert payload["command_health"]["system"]["label"] == "reconnecting"
    assert payload["command_health"]["gpu"]["state"] == "retrying"
    assert payload["command_health"]["gpu"]["label"] == "reconnecting"


def test_metrics_stream_transport_latency_rejects_clock_skew_and_implausible_outliers():
    from server_monitor.dashboard.runtime import _metrics_stream_transport_latency_ms

    received_at = datetime(2026, 3, 13, 12, 0, 0, tzinfo=UTC)

    assert (
        _metrics_stream_transport_latency_ms(
            sample_server_time="2026-03-13T12:00:02+00:00",
            received_at=received_at,
            sample_interval_ms=250,
        )
        is None
    )
    assert (
        _metrics_stream_transport_latency_ms(
            sample_server_time="2026-03-13T11:59:50+00:00",
            received_at=received_at,
            sample_interval_ms=250,
        )
        is None
    )
    assert (
        _metrics_stream_transport_latency_ms(
            sample_server_time="2026-03-13T11:59:59.680+00:00",
            received_at=received_at,
            sample_interval_ms=250,
        )
        == 320
    )
