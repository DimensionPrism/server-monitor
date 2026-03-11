"""Background polling runtime for dashboard live updates."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import re
import time

from server_monitor.dashboard.command_policy import (
    CommandHealthRecord,
    CommandKind,
    CommandPolicy,
    FailureTracker,
    classify_failure,
    default_command_policies,
)
from server_monitor.dashboard.command_runner import CommandRunner
from server_monitor.dashboard.parsers.clash import parse_clash_status
from server_monitor.dashboard.parsers.git_status import parse_repo_status
from server_monitor.dashboard.parsers.gpu import parse_gpu_snapshot
from server_monitor.dashboard.parsers.system import parse_system_snapshot
from server_monitor.dashboard.normalize import normalize_server_payload
from server_monitor.dashboard.settings import DashboardSettingsStore, ServerSettings
from server_monitor.dashboard.terminal_launcher import open_terminal_with_ssh
from server_monitor.dashboard.ws_hub import WebSocketHub


DEFAULT_CLASH = {
    "running": False,
    "api_reachable": False,
    "ui_reachable": False,
    "message": "not-collected",
    "ip_location": "",
    "controller_port": "",
}
GIT_OPERATION_TIMEOUT_SECONDS = 20.0
STATUS_COMMAND_TIMEOUT_SECONDS = 3.0
STATUS_POLL_INLINE_BUDGET_SECONDS = 0.05
COMMAND_HEALTH_HISTORY_LIMIT = 20


@dataclass(slots=True)
class _PolicyExecutionOutcome:
    result: object
    parsed: object | None
    failure_class: str
    attempt_count: int
    message: str
    had_host_unreachable: bool = False
    host_unreachable_message: str = ""


@dataclass(slots=True)
class _SkippedCommandResult:
    stdout: str = ""
    stderr: str = ""
    exit_code: int = -1
    error: str | None = "cooldown_skip"


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
        terminal_launcher=open_terminal_with_ssh,
        stale_after_seconds: float = 15.0,
    ) -> None:
        self.hub = hub
        self.settings_store = settings_store
        self.executor = executor
        self.terminal_launcher = terminal_launcher
        self.stale_after_seconds = stale_after_seconds
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()
        self._last_status_poll: dict[str, datetime] = {}
        self._system_cache: dict[str, dict[str, float]] = {}
        self._system_last_updated_at: dict[str, str] = {}
        self._gpu_cache: dict[str, list[dict]] = {}
        self._gpu_last_updated_at: dict[str, str] = {}
        self._git_last_updated_at: dict[str, str] = {}
        self._repo_cache: dict[str, list[dict]] = {}
        self._clash_cache: dict[str, dict] = {}
        self._clash_last_updated_at: dict[str, str] = {}
        self._system_last_poll_ok: dict[str, bool] = {}
        self._gpu_last_poll_ok: dict[str, bool] = {}
        self._git_last_poll_ok: dict[str, bool] = {}
        self._clash_last_poll_ok: dict[str, bool] = {}
        self._repo_last_poll_ok: dict[str, dict[str, bool]] = {}
        self._status_poll_tasks: dict[str, asyncio.Task] = {}
        self._command_policies = default_command_policies()
        self._recent_command_health: dict[tuple[str, str, str], list[CommandHealthRecord]] = {}
        self._failure_trackers: dict[tuple[str, str, str], FailureTracker] = {}

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run_loop(), name="dashboard-runtime-loop")

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task is not None:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        status_tasks = list(self._status_poll_tasks.values())
        for task in status_tasks:
            task.cancel()
        for task in status_tasks:
            with suppress(asyncio.CancelledError):
                await task
        self._status_poll_tasks.clear()

    async def poll_once(self) -> None:
        settings = self.settings_store.load()
        now = datetime.now(UTC)
        tasks = [
            self._poll_server(
                server=server,
                now=now,
                metrics_interval_seconds=settings.metrics_interval_seconds,
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
        metrics_interval_seconds: float,
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
            metric_tasks["system"] = asyncio.create_task(
                self._execute_with_policy(
                    server_id=server.server_id,
                    ssh_alias=server.ssh_alias,
                    command_kind=CommandKind.SYSTEM,
                    target_label="server",
                    remote_command=_system_command(),
                    policy=self._command_policies[CommandKind.SYSTEM],
                    parse_output=parse_system_snapshot,
                    cache_used=server.server_id in self._system_cache,
                )
            )
        if "gpu" in enabled:
            metric_tasks["gpu"] = asyncio.create_task(
                self._execute_with_policy(
                    server_id=server.server_id,
                    ssh_alias=server.ssh_alias,
                    command_kind=CommandKind.GPU,
                    target_label="server",
                    remote_command=_gpu_command(),
                    policy=self._command_policies[CommandKind.GPU],
                    parse_output=parse_gpu_snapshot,
                    cache_used=server.server_id in self._gpu_cache,
                )
            )

        metric_results: dict[str, object] = {}
        if metric_tasks:
            gathered = await asyncio.gather(*metric_tasks.values())
            for key, result in zip(metric_tasks.keys(), gathered):
                metric_results[key] = result

        if "system" in metric_results:
            system_execution = metric_results["system"]
            if system_execution.failure_class == "ok":
                parsed_system = system_execution.parsed
                snapshot.update(parsed_system)
                self._system_cache[server.server_id] = parsed_system
                system_updated_at = now.isoformat()
                self._system_last_updated_at[server.server_id] = system_updated_at
                self._system_last_poll_ok[server.server_id] = True
                snapshot["metadata"]["system_last_updated_at"] = system_updated_at
                if system_execution.had_host_unreachable:
                    snapshot["metadata"]["ssh_error"] = system_execution.host_unreachable_message or "timeout"
                    host_unreachable = True
            elif system_execution.failure_class == "parse_error":
                self._system_last_poll_ok[server.server_id] = False
                snapshot["metadata"]["metrics_error"] = f"system parse failed: {system_execution.message}"
                if system_execution.had_host_unreachable:
                    snapshot["metadata"]["ssh_error"] = system_execution.host_unreachable_message or "timeout"
                    host_unreachable = True
            else:
                error_text = system_execution.message or "system failed"
                self._system_last_poll_ok[server.server_id] = False
                snapshot["metadata"]["metrics_error"] = error_text
                if system_execution.had_host_unreachable or _is_ssh_unreachable(system_execution.result):
                    snapshot["metadata"]["ssh_error"] = system_execution.host_unreachable_message or error_text
                    host_unreachable = True

        if "gpu" in metric_results:
            gpu_execution = metric_results["gpu"]
            if gpu_execution.failure_class == "ok":
                parsed_gpus = gpu_execution.parsed
                snapshot["gpus"] = parsed_gpus
                self._gpu_cache[server.server_id] = parsed_gpus
                gpu_updated_at = now.isoformat()
                self._gpu_last_updated_at[server.server_id] = gpu_updated_at
                self._gpu_last_poll_ok[server.server_id] = True
                snapshot["metadata"]["gpu_last_updated_at"] = gpu_updated_at
                if gpu_execution.had_host_unreachable:
                    snapshot["metadata"]["ssh_error"] = gpu_execution.host_unreachable_message or "timeout"
                    host_unreachable = True
            elif gpu_execution.failure_class == "parse_error":
                self._gpu_last_poll_ok[server.server_id] = False
                snapshot["metadata"]["gpu_error"] = f"gpu parse failed: {gpu_execution.message}"
                if gpu_execution.had_host_unreachable:
                    snapshot["metadata"]["ssh_error"] = gpu_execution.host_unreachable_message or "timeout"
                    host_unreachable = True
            else:
                error_text = gpu_execution.message or "gpu failed"
                self._gpu_last_poll_ok[server.server_id] = False
                snapshot["metadata"]["gpu_error"] = error_text
                if gpu_execution.had_host_unreachable or _is_ssh_unreachable(gpu_execution.result):
                    snapshot["metadata"]["ssh_error"] = gpu_execution.host_unreachable_message or error_text
                    host_unreachable = True

        should_poll_status = _needs_status_poll(
            last=self._last_status_poll.get(server.server_id),
            now=now,
            interval_seconds=status_interval_seconds,
        )

        self._consume_finished_status_poll_task(server.server_id)

        if should_poll_status and ("git" in enabled or "clash" in enabled) and not host_unreachable:
            await self._start_status_poll_if_needed(server=server, now=now)
        elif should_poll_status and host_unreachable:
            if "git" in enabled:
                self._git_last_poll_ok[server.server_id] = False
            if "clash" in enabled:
                self._clash_last_poll_ok[server.server_id] = False

        repos = [
            repo
            for repo in self._repo_cache.get(server.server_id, [])
            if isinstance(repo, dict) and repo.get("path") in set(server.working_dirs)
        ]
        clash = dict(self._clash_cache.get(server.server_id, DEFAULT_CLASH))
        if server.server_id in self._clash_last_updated_at:
            clash["last_updated_at"] = self._clash_last_updated_at[server.server_id]

        if "git" not in enabled:
            repos = []
        if "clash" not in enabled:
            clash = DEFAULT_CLASH

        metrics_threshold_seconds = max(1.0, metrics_interval_seconds * 2)
        status_threshold_seconds = max(1.0, status_interval_seconds * 2)
        repo_poll_ok = self._repo_last_poll_ok.get(server.server_id, {})
        repos_with_freshness: list[dict] = []
        for repo in repos:
            normalized_repo = dict(repo)
            repo_path = normalized_repo.get("path")
            repo_last_poll_ok = repo_poll_ok.get(repo_path) if isinstance(repo_path, str) else None
            normalized_repo["freshness"] = _build_freshness_entry(
                now=now,
                last_updated_at=normalized_repo.get("last_updated_at"),
                last_poll_ok=repo_last_poll_ok,
                threshold_seconds=status_threshold_seconds,
            )
            repos_with_freshness.append(normalized_repo)

        freshness = {
            "system": _build_freshness_entry(
                now=now,
                last_updated_at=self._system_last_updated_at.get(server.server_id),
                last_poll_ok=self._system_last_poll_ok.get(server.server_id),
                threshold_seconds=metrics_threshold_seconds,
            ),
            "gpu": _build_freshness_entry(
                now=now,
                last_updated_at=self._gpu_last_updated_at.get(server.server_id),
                last_poll_ok=self._gpu_last_poll_ok.get(server.server_id),
                threshold_seconds=metrics_threshold_seconds,
            ),
            "git": _build_freshness_entry(
                now=now,
                last_updated_at=self._git_last_updated_at.get(server.server_id),
                last_poll_ok=self._git_last_poll_ok.get(server.server_id),
                threshold_seconds=status_threshold_seconds,
                keep_live_while_inflight=self._is_status_poll_inflight(server.server_id),
            ),
            "clash": _build_freshness_entry(
                now=now,
                last_updated_at=self._clash_last_updated_at.get(server.server_id),
                last_poll_ok=self._clash_last_poll_ok.get(server.server_id),
                threshold_seconds=status_threshold_seconds,
                keep_live_while_inflight=self._is_status_poll_inflight(server.server_id),
            ),
        }

        payload = {
            "timestamp": snapshot.get("timestamp", now.isoformat()),
            "snapshot": snapshot,
            "repos": repos_with_freshness,
            "clash": clash,
            "enabled_panels": server.enabled_panels,
            "freshness": freshness,
        }
        normalized = normalize_server_payload(
            server_id=server.server_id,
            payload=payload,
            now=now,
            stale_after_seconds=self.stale_after_seconds,
        )
        await self.hub.broadcast(normalized)

    def _is_status_poll_inflight(self, server_id: str) -> bool:
        task = self._status_poll_tasks.get(server_id)
        return task is not None and not task.done()

    def _consume_finished_status_poll_task(self, server_id: str) -> None:
        task = self._status_poll_tasks.get(server_id)
        if task is None or not task.done():
            return
        self._consume_status_poll_task_result(server_id, task)

    def _consume_status_poll_task_result(self, server_id: str, task: asyncio.Task) -> None:
        current = self._status_poll_tasks.get(server_id)
        if current is task:
            self._status_poll_tasks.pop(server_id, None)
        with suppress(asyncio.CancelledError):
            try:
                task.result()
            except Exception:
                self._git_last_poll_ok[server_id] = False
                self._clash_last_poll_ok[server_id] = False

    async def _start_status_poll_if_needed(self, *, server: ServerSettings, now: datetime) -> None:
        existing = self._status_poll_tasks.get(server.server_id)
        if existing is not None:
            if existing.done():
                self._consume_status_poll_task_result(server.server_id, existing)
            else:
                return

        poll_task = asyncio.create_task(
            self._poll_status_panels(server=server, polled_at_iso=now.isoformat()),
            name=f"dashboard-status-poll-{server.server_id}",
        )
        self._status_poll_tasks[server.server_id] = poll_task
        self._last_status_poll[server.server_id] = now

        try:
            await asyncio.wait_for(asyncio.shield(poll_task), timeout=STATUS_POLL_INLINE_BUDGET_SECONDS)
        except asyncio.TimeoutError:
            return
        finally:
            self._consume_finished_status_poll_task(server.server_id)

    async def _poll_status_panels(self, *, server: ServerSettings, polled_at_iso: str) -> None:
        enabled = set(server.enabled_panels)
        allowed_paths = set(server.working_dirs)
        previous_repos = [
            repo for repo in self._repo_cache.get(server.server_id, []) if repo.get("path") in allowed_paths
        ]
        status_tasks: dict[str, asyncio.Task] = {}

        if "git" in enabled:
            status_tasks["git"] = asyncio.create_task(
                self._poll_git_repos(server, previous_repos=previous_repos, polled_at_iso=polled_at_iso)
            )

        if "clash" in enabled:
            secret_execution = await self._execute_with_policy(
                server_id=server.server_id,
                ssh_alias=server.ssh_alias,
                command_kind=CommandKind.CLASH_SECRET,
                target_label="server",
                remote_command=_clash_secret_command(),
                policy=self._command_policies[CommandKind.CLASH_SECRET],
                parse_output=_parse_required_clash_secret,
                cache_used=server.server_id in self._clash_cache,
            )
            if secret_execution.failure_class == "ok":
                status_tasks["clash"] = asyncio.create_task(
                    self._execute_with_policy(
                        server_id=server.server_id,
                        ssh_alias=server.ssh_alias,
                        command_kind=CommandKind.CLASH_PROBE,
                        target_label="server",
                        remote_command=_clash_command(
                            api_probe_url=server.clash_api_probe_url,
                            ui_probe_url=server.clash_ui_probe_url,
                            secret=secret_execution.parsed,
                        ),
                        policy=self._command_policies[CommandKind.CLASH_PROBE],
                        parse_output=parse_clash_status,
                        cache_used=server.server_id in self._clash_cache,
                    )
                )
            elif secret_execution.failure_class == "parse_error" and secret_execution.message == "secret-unavailable":
                clash = dict(self._clash_cache.get(server.server_id, DEFAULT_CLASH))
                clash["api_reachable"] = False
                clash["ui_reachable"] = False
                clash["message"] = "secret-unavailable"
                clash["last_updated_at"] = polled_at_iso
                self._clash_cache[server.server_id] = clash
                self._clash_last_updated_at[server.server_id] = polled_at_iso
                self._clash_last_poll_ok[server.server_id] = False
            else:
                # Transient secret command failures should not overwrite last good clash snapshot.
                self._clash_last_poll_ok[server.server_id] = False

        status_results: dict[str, object] = {}
        if status_tasks:
            gathered = await asyncio.gather(*status_tasks.values(), return_exceptions=True)
            for key, result in zip(status_tasks.keys(), gathered):
                status_results[key] = result

        if "git" in status_results:
            git_result = status_results["git"]
            if isinstance(git_result, Exception):
                self._git_last_poll_ok[server.server_id] = False
            else:
                polled_repos, successful_polls, repo_poll_ok = git_result
                total_repos = len(server.working_dirs)
                self._git_last_poll_ok[server.server_id] = successful_polls == total_repos
                self._repo_last_poll_ok[server.server_id] = repo_poll_ok
                if successful_polls > 0 or len(previous_repos) == 0:
                    self._repo_cache[server.server_id] = polled_repos
                    self._git_last_updated_at[server.server_id] = polled_at_iso

        if "clash" in status_results:
            clash_execution = status_results["clash"]
            if isinstance(clash_execution, Exception):
                self._clash_last_poll_ok[server.server_id] = False
            elif clash_execution.failure_class == "ok":
                clash = clash_execution.parsed
                clash["last_updated_at"] = polled_at_iso
                self._clash_cache[server.server_id] = clash
                self._clash_last_updated_at[server.server_id] = polled_at_iso
                self._clash_last_poll_ok[server.server_id] = True
            else:
                self._clash_last_poll_ok[server.server_id] = False

    async def _poll_git_repos(
        self,
        server: ServerSettings,
        *,
        previous_repos: list[dict],
        polled_at_iso: str,
    ) -> tuple[list[dict], int, dict[str, bool]]:
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
            return [], 0, {}

        repos: list[dict] = []
        successful_polls = 0
        repo_poll_ok: dict[str, bool] = {}
        results = await asyncio.gather(*repo_tasks)
        for repo_path, repo_result, success in results:
            repo_poll_ok[repo_path] = success
            if repo_result is not None:
                repos.append(repo_result)
            if success:
                successful_polls += 1
        return repos, successful_polls, repo_poll_ok

    async def _poll_single_git_repo(
        self,
        *,
        server: ServerSettings,
        repo_path: str,
        previous_repo: dict | None,
        polled_at_iso: str,
    ) -> tuple[str, dict | None, bool]:
        command = _git_status_command(repo_path)
        execution = await self._execute_with_policy(
            server_id=server.server_id,
            ssh_alias=server.ssh_alias,
            command_kind=CommandKind.GIT_STATUS,
            target_label=repo_path,
            remote_command=command,
            policy=self._command_policies[CommandKind.GIT_STATUS],
            parse_output=lambda stdout: parse_repo_status(
                path=repo_path,
                porcelain_text=stdout,
                last_commit_age_seconds=0,
            ),
            cache_used=previous_repo is not None,
        )
        if execution.failure_class != "ok":
            return repo_path, previous_repo, False
        repo = execution.parsed
        repo["last_updated_at"] = polled_at_iso
        return (repo_path, repo, True)

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

    async def open_repo_terminal(self, *, server_id: str, repo_path: str) -> dict:
        settings = self.settings_store.load()
        server = _find_server(settings.servers, server_id)
        if repo_path not in server.working_dirs:
            raise ValueError(f"repo '{repo_path}' is not configured for server '{server_id}'")

        launched = self.terminal_launcher(ssh_alias=server.ssh_alias, repo_path=repo_path)
        return {
            "ok": bool(getattr(launched, "ok", False)),
            "launched_with": str(getattr(launched, "launched_with", "")),
            "detail": str(getattr(launched, "detail", "")),
        }

    async def _run_executor(self, alias: str, remote_command: str, *, timeout_seconds: float):
        try:
            return await self.executor.run(alias, remote_command, timeout_seconds=timeout_seconds)
        except TypeError:
            return await self.executor.run(alias, remote_command)

    async def _execute_with_policy(
        self,
        *,
        server_id: str,
        ssh_alias: str,
        command_kind: CommandKind,
        target_label: str,
        remote_command: str,
        policy: CommandPolicy,
        parse_output=None,
        cache_used: bool,
    ) -> _PolicyExecutionOutcome:
        attempt_durations_ms: list[int] = []
        had_host_unreachable = False
        host_unreachable_message = ""
        tracker = self._failure_tracker_for(
            server_id=server_id,
            command_kind=command_kind,
            target_label=target_label,
            policy=policy,
        )
        if tracker.in_cooldown(now=time.monotonic()):
            skipped_result = _SkippedCommandResult()
            self._append_command_health(
                CommandHealthRecord(
                    recorded_at=datetime.now(UTC).isoformat(),
                    server_id=server_id,
                    command_kind=command_kind,
                    target_label=target_label,
                    ok=False,
                    failure_class="cooldown_skip",
                    attempt_count=0,
                    duration_ms=0,
                    attempt_durations_ms=[],
                    exit_code=skipped_result.exit_code,
                    cooldown_applied=True,
                    cache_used=cache_used,
                    message="cooldown active",
                )
            )
            return _PolicyExecutionOutcome(
                result=skipped_result,
                parsed=None,
                failure_class="cooldown_skip",
                attempt_count=0,
                message="cooldown active",
                had_host_unreachable=False,
                host_unreachable_message="",
            )

        for attempt in range(1, policy.max_attempts + 1):
            started_at = time.monotonic()
            result = await self._run_executor(
                ssh_alias,
                remote_command,
                timeout_seconds=policy.timeout_seconds,
            )
            measured_duration_ms = int((time.monotonic() - started_at) * 1000)
            duration_ms = int(getattr(result, "duration_ms", measured_duration_ms))
            attempt_durations_ms.append(duration_ms)

            if result.exit_code == 0 and not result.error:
                if parse_output is not None:
                    try:
                        parsed = parse_output(result.stdout)
                    except Exception as exc:
                        message = str(exc)
                        cooldown_applied = tracker.record_failure(now=time.monotonic())
                        self._append_command_health(
                            CommandHealthRecord(
                                recorded_at=datetime.now(UTC).isoformat(),
                                server_id=server_id,
                                command_kind=command_kind,
                                target_label=target_label,
                                ok=False,
                                failure_class="parse_error",
                                attempt_count=attempt,
                                duration_ms=sum(attempt_durations_ms),
                                attempt_durations_ms=list(attempt_durations_ms),
                                exit_code=int(getattr(result, "exit_code", -1)),
                                cooldown_applied=cooldown_applied,
                                cache_used=cache_used,
                                message=message,
                            )
                        )
                        return _PolicyExecutionOutcome(
                            result=result,
                            parsed=None,
                            failure_class="parse_error",
                            attempt_count=attempt,
                            message=message,
                            had_host_unreachable=had_host_unreachable,
                            host_unreachable_message=host_unreachable_message,
                        )
                else:
                    parsed = None

                tracker.record_success()
                self._append_command_health(
                    CommandHealthRecord(
                        recorded_at=datetime.now(UTC).isoformat(),
                        server_id=server_id,
                        command_kind=command_kind,
                        target_label=target_label,
                        ok=True,
                        failure_class="ok",
                        attempt_count=attempt,
                        duration_ms=sum(attempt_durations_ms),
                        attempt_durations_ms=list(attempt_durations_ms),
                        exit_code=int(getattr(result, "exit_code", 0)),
                        cooldown_applied=False,
                        cache_used=False,
                        message="",
                    )
                )
                return _PolicyExecutionOutcome(
                    result=result,
                    parsed=parsed,
                    failure_class="ok",
                    attempt_count=attempt,
                    message="",
                    had_host_unreachable=had_host_unreachable,
                    host_unreachable_message=host_unreachable_message,
                )

            failure_class = classify_failure(
                error=getattr(result, "error", None),
                stderr=str(getattr(result, "stderr", "")),
            )
            message = str(getattr(result, "error", "") or getattr(result, "stderr", "") or command_kind.value)
            if _is_ssh_unreachable(result):
                had_host_unreachable = True
                if not host_unreachable_message:
                    host_unreachable_message = message
            if attempt < policy.max_attempts and _should_retry(policy=policy, failure_class=failure_class):
                await asyncio.sleep(policy.base_backoff_seconds * attempt)
                continue

            cooldown_applied = tracker.record_failure(now=time.monotonic())
            self._append_command_health(
                CommandHealthRecord(
                    recorded_at=datetime.now(UTC).isoformat(),
                    server_id=server_id,
                    command_kind=command_kind,
                    target_label=target_label,
                    ok=False,
                    failure_class=failure_class,
                    attempt_count=attempt,
                    duration_ms=sum(attempt_durations_ms),
                    attempt_durations_ms=list(attempt_durations_ms),
                    exit_code=int(getattr(result, "exit_code", -1)),
                    cooldown_applied=cooldown_applied,
                    cache_used=cache_used,
                    message=message,
                )
            )
            return _PolicyExecutionOutcome(
                result=result,
                parsed=None,
                failure_class=failure_class,
                attempt_count=attempt,
                message=message,
                had_host_unreachable=had_host_unreachable,
                host_unreachable_message=host_unreachable_message,
            )

        raise RuntimeError("policy execution exited without result")

    def _append_command_health(self, record: CommandHealthRecord) -> None:
        key = (record.server_id, record.command_kind.value, record.target_label)
        history = self._recent_command_health.setdefault(key, [])
        history.append(record)
        if len(history) > COMMAND_HEALTH_HISTORY_LIMIT:
            history.pop(0)

    def _failure_tracker_for(
        self,
        *,
        server_id: str,
        command_kind: CommandKind,
        target_label: str,
        policy: CommandPolicy,
    ) -> FailureTracker:
        key = (server_id, command_kind.value, target_label)
        tracker = self._failure_trackers.get(key)
        if tracker is None:
            tracker = FailureTracker(
                cooldown_after_failures=policy.cooldown_after_failures,
                cooldown_seconds=policy.cooldown_seconds,
            )
            self._failure_trackers[key] = tracker
        return tracker

    def get_recent_command_health(
        self,
        *,
        server_id: str,
        command_kind: str | None = None,
        target_label: str | None = None,
    ) -> list[dict]:
        matching: list[dict] = []
        for (record_server_id, record_command_kind, record_target_label), records in self._recent_command_health.items():
            if record_server_id != server_id:
                continue
            if command_kind is not None and record_command_kind != command_kind:
                continue
            if target_label is not None and record_target_label != target_label:
                continue
            matching.extend(asdict(record) for record in records)
        return matching

    def build_diagnostics_bundle(self) -> dict:
        settings = self.settings_store.load()
        servers: dict[str, dict] = {}

        for (server_id, command_kind, target_label), records in sorted(self._recent_command_health.items()):
            server_entry = servers.setdefault(server_id, {"server_id": server_id, "commands": []})
            recent_outcomes = [
                {
                    "recorded_at": record.recorded_at,
                    "server_id": record.server_id,
                    "command_kind": record.command_kind.value,
                    "target_label": record.target_label,
                    "ok": record.ok,
                    "failure_class": record.failure_class,
                    "attempt_count": record.attempt_count,
                    "duration_ms": record.duration_ms,
                    "attempt_durations_ms": list(record.attempt_durations_ms),
                    "exit_code": record.exit_code,
                    "cooldown_applied": record.cooldown_applied,
                    "cache_used": record.cache_used,
                    "message": record.message,
                }
                for record in records
            ]
            success_count = sum(1 for record in records if record.ok)
            failure_count = len(records) - success_count
            avg_duration_ms = int(sum(record.duration_ms for record in records) / len(records)) if records else 0
            last_failure_class = next((record.failure_class for record in reversed(records) if not record.ok), "ok")
            server_entry["commands"].append(
                {
                    "command_kind": command_kind,
                    "target_label": target_label,
                    "recent_outcomes": recent_outcomes,
                    "summary": {
                        "success_count": success_count,
                        "failure_count": failure_count,
                        "avg_duration_ms": avg_duration_ms,
                        "last_failure_class": last_failure_class,
                    },
                }
            )

        return {
            "generated_at": datetime.now(UTC).isoformat(),
            "settings": _serialize_runtime_settings(settings),
            "servers": [servers[server_id] for server_id in sorted(servers.keys())],
        }

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


def _serialize_runtime_settings(settings) -> dict:
    return {
        "metrics_interval_seconds": settings.metrics_interval_seconds,
        "status_interval_seconds": settings.status_interval_seconds,
        "servers": [
            {
                "server_id": server.server_id,
                "ssh_alias": server.ssh_alias,
                "working_dirs": list(server.working_dirs),
                "enabled_panels": list(server.enabled_panels),
                "clash_api_probe_url": server.clash_api_probe_url,
                "clash_ui_probe_url": server.clash_ui_probe_url,
            }
            for server in settings.servers
        ],
    }


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


def _should_retry(*, policy: CommandPolicy, failure_class: str) -> bool:
    if failure_class == "timeout":
        return policy.retry_on_timeout
    if failure_class == "ssh_unreachable":
        return policy.retry_on_ssh_error
    if failure_class == "nonzero_exit":
        return policy.retry_on_nonzero_exit
    return False


def _build_freshness_entry(
    *,
    now: datetime,
    last_updated_at: str | None,
    last_poll_ok: bool | None,
    threshold_seconds: float,
    keep_live_while_inflight: bool = False,
) -> dict[str, str | int | float | None]:
    age_seconds = _age_seconds_from_iso(now=now, timestamp_iso=last_updated_at)
    normalized_threshold = float(max(1.0, threshold_seconds))

    if last_poll_ok is False:
        state = "cached"
        reason = "poll_error"
    elif age_seconds is None:
        state = "cached"
        reason = "no_data"
    elif age_seconds > normalized_threshold:
        if keep_live_while_inflight:
            state = "live"
            reason = "poll_inflight"
        else:
            state = "cached"
            reason = "age_expired"
    else:
        state = "live"
        reason = "ok"

    return {
        "state": state,
        "reason": reason,
        "last_updated_at": last_updated_at,
        "age_seconds": age_seconds if age_seconds is not None else 0,
        "threshold_seconds": normalized_threshold,
    }


def _age_seconds_from_iso(*, now: datetime, timestamp_iso: str | None) -> int | None:
    if not timestamp_iso:
        return None
    try:
        parsed = datetime.fromisoformat(timestamp_iso)
    except ValueError:
        return None
    return max(0, int((now - parsed).total_seconds()))


def _extract_clash_secret(output: str) -> str | None:
    if not output:
        return None
    ansi_cleaned = re.sub(r"\x1b\[[0-9;]*m", "", output)
    patterns = [
        r"当前密钥\s*[:：]\s*(\S+)",
        r"current\s+secret\s*[:：]\s*(\S+)",
        r"secret\s*[:：]\s*(\S+)",
    ]
    for raw_line in ansi_cleaned.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        for pattern in patterns:
            match = re.search(pattern, line, flags=re.IGNORECASE)
            if match:
                secret = match.group(1).strip().strip("'\"")
                if secret:
                    return secret
    return None


def _parse_required_clash_secret(output: str) -> str:
    secret = _extract_clash_secret(output)
    if secret:
        return secret
    raise ValueError("secret-unavailable")


def _clash_secret_command() -> str:
    return (
        "if command -v clashsecret >/dev/null 2>&1; then "
        "clashsecret; "
        "elif command -v clashctl >/dev/null 2>&1; then "
        "clashctl secret; "
        "else "
        "for CANDIDATE in "
        "$HOME/clashctl/resources/runtime.yaml "
        "$HOME/clash-for-linux-install/resources/runtime.yaml "
        "; do "
        "if [ -r \"$CANDIDATE\" ]; then "
        "SECRET=$(sed -n 's/^secret:[[:space:]]*//p' \"$CANDIDATE\" | head -n1 | tr -d '\\r' | xargs); "
        "if [ -n \"$SECRET\" ]; then echo \"当前密钥：$SECRET\"; exit 0; fi; "
        "fi; "
        "done; "
        "echo 'secret-unavailable' >&2; "
        "exit 1; "
        "fi"
    )


def _clash_command(
    api_probe_url: str = "http://127.0.0.1:9090/version",
    ui_probe_url: str = "http://127.0.0.1:9090/ui",
    secret: str = "",
) -> str:
    auth_header = _shell_quote(f"Authorization: Bearer {secret}")
    api_url = _shell_quote(api_probe_url)
    ui_url = _shell_quote(ui_probe_url)
    return (
        "if pgrep -f clash >/dev/null; then echo running=true; else echo running=false; fi; "
        f"AUTH_HEADER={auth_header}; "
        f"API_URL={api_url}; "
        f"UI_URL={ui_url}; "
        "if command -v curl >/dev/null 2>&1; then "
        "API_CODE=$(curl -sS -o /dev/null -w '%{http_code}' --connect-timeout 1 --max-time 2 -H \"$AUTH_HEADER\" \"$API_URL\" || echo 000); "
        "UI_CODE=$(curl -sS -o /dev/null -w '%{http_code}' --connect-timeout 1 --max-time 2 -H \"$AUTH_HEADER\" \"$UI_URL\" || echo 000); "
        "if [ \"$API_CODE\" -ge 200 ] && [ \"$API_CODE\" -lt 400 ]; then echo api_reachable=true; else echo api_reachable=false; fi; "
        "if [ \"$UI_CODE\" -ge 200 ] && [ \"$UI_CODE\" -lt 400 ]; then echo ui_reachable=true; else echo ui_reachable=false; fi; "
        "if [ \"$API_CODE\" -ge 200 ] && [ \"$API_CODE\" -lt 400 ] && [ \"$UI_CODE\" -ge 200 ] && [ \"$UI_CODE\" -lt 400 ]; then echo message=ok; else echo message=probe-error; fi; "
        "CTRL_PORT=unknown; "
        "PROXY_URL=; "
        "for CANDIDATE in "
        "$HOME/clashctl/resources/runtime.yaml "
        "$HOME/clash-for-linux-install/resources/runtime.yaml "
        "; do "
        "if [ -r \"$CANDIDATE\" ]; then "
        "CTRL_LINE=$(grep -m1 '^external-controller:' \"$CANDIDATE\" | cut -d: -f2- | tr -d '\"' | tr -d \"'\" | tr -d '\\r' | xargs); "
        "if [ -n \"$CTRL_LINE\" ]; then "
        "CTRL_PORT=$(printf '%s' \"$CTRL_LINE\" | awk -F: '{print $NF}' | tr -d '\\r' | xargs); "
        "fi; "
        "PROXY_PORT=$(grep -m1 '^mixed-port:' \"$CANDIDATE\" | cut -d: -f2- | tr -d '\\r' | xargs); "
        "if [ -z \"$PROXY_PORT\" ]; then "
        "PROXY_PORT=$(grep -m1 '^port:' \"$CANDIDATE\" | cut -d: -f2- | tr -d '\\r' | xargs); "
        "fi; "
        "if [ -n \"$PROXY_PORT\" ]; then PROXY_URL=\"http://127.0.0.1:$PROXY_PORT\"; fi; "
        "if [ -n \"$CTRL_PORT\" ] && [ -n \"$PROXY_URL\" ]; then break; fi; "
        "fi; "
        "done; "
        "IP_LOCATION=unknown; "
        "if [ -n \"$PROXY_URL\" ]; then "
        "IP_INFO=$(curl -sS --proxy \"$PROXY_URL\" --connect-timeout 1 --max-time 2 'http://ip-api.com/line/?fields=query,country,regionName,city' || true); "
        "else "
        "IP_INFO=$(curl -sS --connect-timeout 1 --max-time 2 'http://ip-api.com/line/?fields=query,country,regionName,city' || true); "
        "fi; "
        "IP_COUNTRY=$(printf '%s\\n' \"$IP_INFO\" | sed -n '1p' | tr -d '\\r'); "
        "IP_REGION=$(printf '%s\\n' \"$IP_INFO\" | sed -n '2p' | tr -d '\\r'); "
        "IP_CITY=$(printf '%s\\n' \"$IP_INFO\" | sed -n '3p' | tr -d '\\r'); "
        "IP_ADDR=$(printf '%s\\n' \"$IP_INFO\" | sed -n '4p' | tr -d '\\r'); "
        "if [ -n \"$IP_ADDR$IP_COUNTRY$IP_REGION$IP_CITY\" ] && [ \"$IP_ADDR\" != \"fail\" ]; then "
        "IP_LOCATION=\"$IP_CITY\"; "
        "if [ -n \"$IP_REGION\" ]; then IP_LOCATION=\"${IP_LOCATION}, ${IP_REGION}\"; fi; "
        "if [ -n \"$IP_COUNTRY\" ]; then IP_LOCATION=\"${IP_LOCATION}, ${IP_COUNTRY}\"; fi; "
        "if [ -n \"$IP_ADDR\" ]; then IP_LOCATION=\"${IP_LOCATION} (${IP_ADDR})\"; fi; "
        "IP_LOCATION=$(printf '%s' \"$IP_LOCATION\" | sed 's/^, //; s/^ *//; s/ *$//'); "
        "fi; "
        "echo ip_location=$IP_LOCATION; "
        "else "
        "echo api_reachable=false; "
        "echo ui_reachable=false; "
        "echo message=curl-missing; "
        "echo ip_location=unknown; "
        "fi; "
        "echo controller_port=$CTRL_PORT"
    )
