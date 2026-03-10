"""Background polling runtime for dashboard live updates."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import UTC, datetime
import re

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
GIT_OPERATION_TIMEOUT_SECONDS = 20.0


class SshCommandExecutor:
    """Execute remote commands over SSH aliases."""

    def __init__(self, *, runner: CommandRunner | None = None) -> None:
        self.runner = runner or CommandRunner(timeout_seconds=3.0)

    async def run(self, alias: str, remote_command: str, timeout_seconds: float | None = None):
        runner = self.runner
        if timeout_seconds is not None and timeout_seconds != self.runner.timeout_seconds:
            runner = CommandRunner(timeout_seconds=timeout_seconds)
        return await runner.run(["ssh", alias, remote_command])


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
        self._system_cache: dict[str, dict[str, float]] = {}
        self._system_last_updated_at: dict[str, str] = {}
        self._gpu_cache: dict[str, list[dict]] = {}
        self._gpu_last_updated_at: dict[str, str] = {}
        self._repo_cache: dict[str, list[dict]] = {}
        self._clash_cache: dict[str, dict] = {}
        self._clash_last_updated_at: dict[str, str] = {}

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
        tasks = [
            self._poll_server(
                server=server,
                now=now,
                status_interval_seconds=settings.status_interval_seconds,
            )
            for server in settings.servers
        ]
        if tasks:
            await asyncio.gather(*tasks)

    async def _run_loop(self) -> None:
        loop = asyncio.get_running_loop()
        while not self._stop_event.is_set():
            cycle_started_at = loop.time()
            await self.poll_once()
            settings = self.settings_store.load()
            elapsed_seconds = loop.time() - cycle_started_at
            await asyncio.sleep(
                _metrics_sleep_seconds(
                    interval_seconds=settings.metrics_interval_seconds,
                    elapsed_seconds=elapsed_seconds,
                )
            )

    async def _poll_server(
        self,
        *,
        server: ServerSettings,
        now: datetime,
        status_interval_seconds: float,
    ) -> None:
        enabled = set(server.enabled_panels)
        cached_system = self._system_cache.get(server.server_id, _empty_system_snapshot())
        cached_gpus = self._gpu_cache.get(server.server_id, [])
        metadata: dict[str, str] = {}
        if server.server_id in self._system_last_updated_at:
            metadata["system_last_updated_at"] = self._system_last_updated_at[server.server_id]
        if server.server_id in self._gpu_last_updated_at:
            metadata["gpu_last_updated_at"] = self._gpu_last_updated_at[server.server_id]
        snapshot = {
            "timestamp": now.isoformat(),
            "cpu_percent": cached_system["cpu_percent"],
            "memory_percent": cached_system["memory_percent"],
            "disk_percent": cached_system["disk_percent"],
            "network_rx_kbps": cached_system["network_rx_kbps"],
            "network_tx_kbps": cached_system["network_tx_kbps"],
            "gpus": [dict(gpu) for gpu in cached_gpus],
            "metadata": metadata,
        }
        host_unreachable = False

        metric_tasks: dict[str, asyncio.Task] = {}
        if "system" in enabled:
            metric_tasks["system"] = asyncio.create_task(self.executor.run(server.ssh_alias, _system_command()))
        if "gpu" in enabled:
            metric_tasks["gpu"] = asyncio.create_task(self.executor.run(server.ssh_alias, _gpu_command()))

        metric_results: dict[str, object] = {}
        if metric_tasks:
            gathered = await asyncio.gather(*metric_tasks.values())
            for key, result in zip(metric_tasks.keys(), gathered):
                metric_results[key] = result

        if "system" in metric_results:
            system_result = metric_results["system"]
            if system_result.exit_code == 0 and not system_result.error:
                try:
                    parsed_system = parse_system_snapshot(system_result.stdout)
                except Exception as exc:
                    snapshot["metadata"]["metrics_error"] = f"system parse failed: {exc}"
                else:
                    snapshot.update(parsed_system)
                    self._system_cache[server.server_id] = parsed_system
                    system_updated_at = now.isoformat()
                    self._system_last_updated_at[server.server_id] = system_updated_at
                    snapshot["metadata"]["system_last_updated_at"] = system_updated_at
            else:
                error_text = system_result.error or system_result.stderr or "system failed"
                snapshot["metadata"]["metrics_error"] = error_text
                if _is_ssh_unreachable(system_result):
                    snapshot["metadata"]["ssh_error"] = error_text
                    host_unreachable = True

        if "gpu" in metric_results:
            gpu_result = metric_results["gpu"]
            if gpu_result.exit_code == 0 and not gpu_result.error:
                try:
                    parsed_gpus = parse_gpu_snapshot(gpu_result.stdout)
                except Exception as exc:
                    snapshot["metadata"]["gpu_error"] = f"gpu parse failed: {exc}"
                else:
                    snapshot["gpus"] = parsed_gpus
                    self._gpu_cache[server.server_id] = parsed_gpus
                    gpu_updated_at = now.isoformat()
                    self._gpu_last_updated_at[server.server_id] = gpu_updated_at
                    snapshot["metadata"]["gpu_last_updated_at"] = gpu_updated_at
            else:
                error_text = gpu_result.error or gpu_result.stderr or "gpu failed"
                snapshot["metadata"]["gpu_error"] = error_text
                if _is_ssh_unreachable(gpu_result):
                    snapshot["metadata"]["ssh_error"] = error_text
                    host_unreachable = True

        repos = self._repo_cache.get(server.server_id, [])
        clash = dict(self._clash_cache.get(server.server_id, DEFAULT_CLASH))
        if server.server_id in self._clash_last_updated_at:
            clash["last_updated_at"] = self._clash_last_updated_at[server.server_id]

        should_poll_status = _needs_status_poll(
            last=self._last_status_poll.get(server.server_id),
            now=now,
            interval_seconds=status_interval_seconds,
        )

        if should_poll_status and ("git" in enabled or "clash" in enabled) and not host_unreachable:
            previous_repos = [
                repo for repo in self._repo_cache.get(server.server_id, []) if repo.get("path") in set(server.working_dirs)
            ]
            status_tasks: dict[str, asyncio.Task] = {}
            if "git" in enabled:
                status_tasks["git"] = asyncio.create_task(
                    self._poll_git_repos(server, previous_repos=previous_repos, polled_at_iso=now.isoformat())
                )
            if "clash" in enabled:
                status_tasks["clash"] = asyncio.create_task(self.executor.run(server.ssh_alias, _clash_command()))

            status_results: dict[str, object] = {}
            if status_tasks:
                gathered = await asyncio.gather(*status_tasks.values())
                for key, result in zip(status_tasks.keys(), gathered):
                    status_results[key] = result

            if "git" in status_results:
                polled_repos, successful_polls = status_results["git"]
                if successful_polls > 0 or len(previous_repos) == 0:
                    repos = polled_repos
                    self._repo_cache[server.server_id] = polled_repos
                else:
                    repos = previous_repos

            if "clash" in status_results:
                clash_result = status_results["clash"]
                if clash_result.exit_code == 0 and not clash_result.error:
                    clash = parse_clash_status(clash_result.stdout)
                    clash_updated_at = now.isoformat()
                    clash["last_updated_at"] = clash_updated_at
                    self._clash_cache[server.server_id] = clash
                    self._clash_last_updated_at[server.server_id] = clash_updated_at
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

    async def _poll_git_repos(
        self,
        server: ServerSettings,
        *,
        previous_repos: list[dict],
        polled_at_iso: str,
    ) -> tuple[list[dict], int]:
        previous_by_path = {
            repo.get("path"): repo
            for repo in previous_repos
            if isinstance(repo, dict) and isinstance(repo.get("path"), str)
        }
        repo_tasks = [
            asyncio.create_task(
                self._poll_single_git_repo(
                    server=server,
                    repo_path=repo,
                    previous_repo=previous_by_path.get(repo),
                    polled_at_iso=polled_at_iso,
                )
            )
            for repo in server.working_dirs
        ]
        if not repo_tasks:
            return [], 0

        repos: list[dict] = []
        successful_polls = 0
        results = await asyncio.gather(*repo_tasks)
        for repo_result, success in results:
            if repo_result is not None:
                repos.append(repo_result)
            if success:
                successful_polls += 1
        return repos, successful_polls

    async def _poll_single_git_repo(
        self,
        *,
        server: ServerSettings,
        repo_path: str,
        previous_repo: dict | None,
        polled_at_iso: str,
    ) -> tuple[dict | None, bool]:
        command = _git_status_command(repo_path)
        result = await self.executor.run(server.ssh_alias, command)
        if result.exit_code != 0 or result.error:
            return previous_repo, False
        repo = parse_repo_status(
            path=repo_path,
            porcelain_text=result.stdout,
            last_commit_age_seconds=0,
        )
        repo["last_updated_at"] = polled_at_iso
        return (repo, True)

    async def run_git_operation(
        self,
        *,
        server_id: str,
        repo_path: str,
        operation: str,
        branch: str | None = None,
    ) -> dict:
        settings = self.settings_store.load()
        server = _find_server(settings.servers, server_id)
        if repo_path not in server.working_dirs:
            raise ValueError(f"repo '{repo_path}' is not configured for server '{server_id}'")

        command = _git_operation_command(repo_path=repo_path, operation=operation, branch=branch)

        if operation == "refresh":
            operation_result = await self._run_executor(
                server.ssh_alias,
                command,
                timeout_seconds=GIT_OPERATION_TIMEOUT_SECONDS,
            )
            status_result = operation_result
        else:
            operation_result = await self._run_executor(
                server.ssh_alias,
                command,
                timeout_seconds=GIT_OPERATION_TIMEOUT_SECONDS,
            )
            status_result = await self._run_executor(
                server.ssh_alias,
                _git_status_command(repo_path),
                timeout_seconds=GIT_OPERATION_TIMEOUT_SECONDS,
            )

        operation_ok = operation_result.exit_code == 0 and not operation_result.error
        stderr_blob = operation_result.error or operation_result.stderr or ""
        if operation == "refresh" and status_result is not operation_result:
            stderr_blob = stderr_blob or status_result.error or status_result.stderr or ""

        if status_result.exit_code == 0 and not status_result.error:
            repo = parse_repo_status(
                path=repo_path,
                porcelain_text=status_result.stdout,
                last_commit_age_seconds=0,
            )
            repo["last_updated_at"] = datetime.now(UTC).isoformat()
            self._replace_cached_repo(server_id=server_id, repo=repo)
        else:
            repo = _empty_repo_status(repo_path)

        return {
            "ok": operation_ok,
            "operation": operation,
            "command": command,
            "stdout": operation_result.stdout,
            "stderr": stderr_blob,
            "exit_code": operation_result.exit_code,
            "repo": repo,
        }

    async def _run_executor(self, alias: str, remote_command: str, *, timeout_seconds: float):
        try:
            return await self.executor.run(alias, remote_command, timeout_seconds=timeout_seconds)
        except TypeError:
            return await self.executor.run(alias, remote_command)

    def _replace_cached_repo(self, *, server_id: str, repo: dict) -> None:
        existing = self._repo_cache.get(server_id, [])
        replaced = False
        updated: list[dict] = []
        for item in existing:
            if item.get("path") == repo.get("path"):
                updated.append(repo)
                replaced = True
            else:
                updated.append(item)
        if not replaced:
            updated.append(repo)
        self._repo_cache[server_id] = updated


def _needs_status_poll(*, last: datetime | None, now: datetime, interval_seconds: float) -> bool:
    if last is None:
        return True
    return (now - last).total_seconds() >= interval_seconds


def _metrics_sleep_seconds(*, interval_seconds: float, elapsed_seconds: float) -> float:
    target_interval_seconds = max(0.5, interval_seconds)
    # Keep loop cadence close to the configured interval while avoiding tight loops.
    return max(0.05, target_interval_seconds - elapsed_seconds)


def _find_server(servers: list[ServerSettings], server_id: str) -> ServerSettings:
    for server in servers:
        if server.server_id == server_id:
            return server
    raise KeyError(f"unknown server '{server_id}'")


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


def _empty_repo_status(path: str) -> dict[str, str | int | bool | None]:
    return {
        "path": path,
        "branch": "unknown",
        "dirty": False,
        "ahead": 0,
        "behind": 0,
        "staged": 0,
        "unstaged": 0,
        "untracked": 0,
        "last_commit_age_seconds": 0,
        "last_updated_at": None,
    }


def _empty_system_snapshot() -> dict[str, float]:
    return {
        "cpu_percent": 0.0,
        "memory_percent": 0.0,
        "disk_percent": 0.0,
        "network_rx_kbps": 0.0,
        "network_tx_kbps": 0.0,
    }


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


SAFE_BRANCH_RE = re.compile(r"^[A-Za-z0-9._/-]+$")


def _git_operation_command(*, repo_path: str, operation: str, branch: str | None) -> str:
    quoted_repo = _shell_quote(repo_path)

    if operation == "refresh":
        return _git_status_command(repo_path)
    if operation == "fetch":
        return f"git -C {quoted_repo} fetch --prune --tags"
    if operation == "pull":
        return f"git -C {quoted_repo} pull --ff-only"
    if operation == "checkout":
        if branch is None or branch.strip() == "":
            raise ValueError("branch is required for checkout")
        normalized_branch = branch.strip()
        if not _is_valid_branch_name(normalized_branch):
            raise ValueError("invalid branch name")
        return f"git -C {quoted_repo} checkout {_shell_quote(normalized_branch)}"
    raise ValueError(f"unsupported operation '{operation}'")


def _is_valid_branch_name(branch: str) -> bool:
    if not SAFE_BRANCH_RE.fullmatch(branch):
        return False
    if branch.startswith("-"):
        return False
    if ".." in branch or "@{" in branch:
        return False
    return True


def _clash_command() -> str:
    return (
        "if pgrep -f clash >/dev/null; then echo running=true; else echo running=false; fi; "
        "echo api_reachable=false; "
        "echo ui_reachable=false; "
        "echo message=ok"
    )
