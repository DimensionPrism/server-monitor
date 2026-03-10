"""Background polling runtime for dashboard live updates."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import UTC, datetime

from server_monitor.agent.command_runner import CommandRunner
from server_monitor.agent.parsers.clash import parse_clash_status
from server_monitor.agent.parsers.git_status import parse_repo_status
from server_monitor.agent.parsers.gpu import parse_gpu_snapshot
from server_monitor.agent.parsers.system import parse_system_snapshot
from server_monitor.dashboard.normalize import normalize_server_payload
from server_monitor.dashboard.settings import DashboardSettingsStore, ServerSettings
from server_monitor.dashboard.ws_hub import WebSocketHub


DEFAULT_CLASH = {
    "running": False,
    "api_reachable": False,
    "ui_reachable": False,
    "message": "not-collected",
}


class SshCommandExecutor:
    """Execute remote commands over SSH aliases."""

    def __init__(self, *, runner: CommandRunner | None = None) -> None:
        self.runner = runner or CommandRunner(timeout_seconds=3.0)

    async def run(self, alias: str, remote_command: str):
        return await self.runner.run(["ssh", alias, remote_command])


class DashboardRuntime:
    """Poll SSH targets and broadcast normalized websocket updates."""

    def __init__(
        self,
        *,
        hub: WebSocketHub,
        settings_store: DashboardSettingsStore,
        executor,
        stale_after_seconds: float = 15.0,
    ) -> None:
        self.hub = hub
        self.settings_store = settings_store
        self.executor = executor
        self.stale_after_seconds = stale_after_seconds
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()
        self._last_status_poll: dict[str, datetime] = {}
        self._repo_cache: dict[str, list[dict]] = {}
        self._clash_cache: dict[str, dict] = {}

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run_loop(), name="dashboard-runtime-loop")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stop_event.set()
        self._task.cancel()
        with suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def poll_once(self) -> None:
        settings = self.settings_store.load()
        now = datetime.now(UTC)
        for server in settings.servers:
            await self._poll_server(
                server=server,
                now=now,
                status_interval_seconds=settings.status_interval_seconds,
            )

    async def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            await self.poll_once()
            settings = self.settings_store.load()
            await asyncio.sleep(max(0.5, settings.metrics_interval_seconds))

    async def _poll_server(
        self,
        *,
        server: ServerSettings,
        now: datetime,
        status_interval_seconds: float,
    ) -> None:
        enabled = set(server.enabled_panels)
        snapshot = {
            "timestamp": now.isoformat(),
            "cpu_percent": 0.0,
            "memory_percent": 0.0,
            "disk_percent": 0.0,
            "network_rx_kbps": 0.0,
            "network_tx_kbps": 0.0,
            "gpus": [],
            "metadata": {},
        }
        host_unreachable = False

        if "system" in enabled:
            system_result = await self.executor.run(server.ssh_alias, _system_command())
            if system_result.exit_code == 0 and not system_result.error:
                snapshot.update(parse_system_snapshot(system_result.stdout))
            else:
                error_text = system_result.error or system_result.stderr or "system failed"
                snapshot["metadata"]["metrics_error"] = error_text
                if _is_ssh_unreachable(system_result):
                    snapshot["metadata"]["ssh_error"] = error_text
                    host_unreachable = True

        if "gpu" in enabled and not host_unreachable:
            gpu_result = await self.executor.run(server.ssh_alias, _gpu_command())
            if gpu_result.exit_code == 0 and not gpu_result.error:
                snapshot["gpus"] = parse_gpu_snapshot(gpu_result.stdout)
            else:
                error_text = gpu_result.error or gpu_result.stderr or "gpu failed"
                snapshot["metadata"]["gpu_error"] = error_text
                if _is_ssh_unreachable(gpu_result):
                    snapshot["metadata"]["ssh_error"] = error_text
                    host_unreachable = True

        repos = self._repo_cache.get(server.server_id, [])
        clash = self._clash_cache.get(server.server_id, DEFAULT_CLASH)

        should_poll_status = _needs_status_poll(
            last=self._last_status_poll.get(server.server_id),
            now=now,
            interval_seconds=status_interval_seconds,
        )

        if should_poll_status and ("git" in enabled or "clash" in enabled) and not host_unreachable:
            if "git" in enabled:
                repos = await self._poll_git_repos(server)
                self._repo_cache[server.server_id] = repos

            if "clash" in enabled:
                clash_result = await self.executor.run(server.ssh_alias, _clash_command())
                if clash_result.exit_code == 0 and not clash_result.error:
                    clash = parse_clash_status(clash_result.stdout)
                    self._clash_cache[server.server_id] = clash
            self._last_status_poll[server.server_id] = now

        if "git" not in enabled:
            repos = []
        if "clash" not in enabled:
            clash = DEFAULT_CLASH

        payload = {
            "timestamp": snapshot.get("timestamp", now.isoformat()),
            "snapshot": snapshot,
            "repos": repos,
            "clash": clash,
            "enabled_panels": server.enabled_panels,
        }
        normalized = normalize_server_payload(
            server_id=server.server_id,
            payload=payload,
            now=now,
            stale_after_seconds=self.stale_after_seconds,
        )
        await self.hub.broadcast(normalized)

    async def _poll_git_repos(self, server: ServerSettings) -> list[dict]:
        repos: list[dict] = []
        for repo in server.working_dirs:
            command = _git_status_command(repo)
            result = await self.executor.run(server.ssh_alias, command)
            if result.exit_code != 0 or result.error:
                continue
            repos.append(
                parse_repo_status(
                    path=repo,
                    porcelain_text=result.stdout,
                    last_commit_age_seconds=0,
                )
            )
        return repos


def _needs_status_poll(*, last: datetime | None, now: datetime, interval_seconds: float) -> bool:
    if last is None:
        return True
    return (now - last).total_seconds() >= interval_seconds


def _is_ssh_unreachable(result) -> bool:
    blob = f"{result.error or ''} {result.stderr or ''}".lower()
    return any(
        token in blob
        for token in [
            "timeout",
            "timed out",
            "could not resolve hostname",
            "connection refused",
            "network is unreachable",
            "no route to host",
        ]
    )


def _shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def _system_command() -> str:
    return (
        "CPU=$(top -bn1 | awk '/Cpu\\(s\\)/ {print 100-$8; exit}'); "
        "MEM=$(free | awk '/Mem:/ {printf \"%.2f\", ($3/$2)*100}'); "
        "DISK=$(df -P / | awk 'NR==2 {gsub(/%/,\"\",$5); print $5}'); "
        "echo \"CPU: ${CPU:-0}\"; "
        "echo \"MEM: ${MEM:-0}\"; "
        "echo \"DISK: ${DISK:-0}\"; "
        "echo \"RX_KBPS: 0\"; "
        "echo \"TX_KBPS: 0\""
    )


def _gpu_command() -> str:
    return "nvidia-smi --query-gpu=index,name,utilization.gpu,memory.used,memory.total,temperature.gpu --format=csv,noheader,nounits"


def _git_status_command(repo: str) -> str:
    return f"git -C {_shell_quote(repo)} status --porcelain --branch"


def _clash_command() -> str:
    return (
        "if pgrep -f clash >/dev/null; then echo running=true; else echo running=false; fi; "
        "echo api_reachable=false; "
        "echo ui_reachable=false; "
        "echo message=ok"
    )
