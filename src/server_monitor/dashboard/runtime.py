"""Background polling runtime for dashboard live updates."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

from server_monitor.dashboard.status_poller import StatusPoller
from server_monitor.dashboard.command_policy import (
    CommandHealthRecord,
    CommandKind,
    CommandPolicy,
    FailureTracker,
    default_command_policies,
)
from server_monitor.dashboard.command_runner import CommandRunner
from server_monitor.dashboard.parsers.git_status import parse_repo_status
from server_monitor.dashboard.normalize import normalize_server_payload
from server_monitor.dashboard.settings import DashboardSettingsStore, ServerSettings
from server_monitor.dashboard.terminal_launcher import open_terminal_with_ssh
from server_monitor.dashboard.ws_hub import WebSocketHub
from server_monitor.dashboard.git_operations import GitOperations
from server_monitor.dashboard.command_health import CommandHealthTracker
from server_monitor.dashboard.command_executor import CommandExecutor
from server_monitor.dashboard.runtime_helpers import (
    DEFAULT_CLASH,
    GIT_OPERATION_TIMEOUT_SECONDS,
    STATUS_COMMAND_TIMEOUT_SECONDS,  # noqa: F401
    _needs_status_poll,
    _metrics_sleep_seconds,
    _git_status_command,
    _git_operation_command,
    _serialize_runtime_settings,
    _is_ssh_unreachable,
    _find_server,
    _build_freshness_entry,
    _metrics_stream_transport_latency_ms,
    _extract_clash_secret,  # noqa: F401
    _empty_repo_status,
)


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


@dataclass(slots=True)
class _MetricsStreamStatus:
    state: str = "unknown"
    last_sample_received_at: str | None = None
    last_sample_server_time: str | None = None
    transport_latency_ms: int | None = None
    last_sequence: int | None = None
    sample_interval_ms: int | None = None
    reconnect_count: int = 0
    state_changed_at: str | None = None


class SshCommandExecutor:
    """Execute remote commands over SSH aliases."""

    def __init__(self, *, runner: CommandRunner | None = None) -> None:
        self.runner = runner or CommandRunner(timeout_seconds=3.0)
        self._alias_locks: dict[str, asyncio.Lock] = {}

    async def run(
        self, alias: str, remote_command: str, timeout_seconds: float | None = None
    ):
        runner = self.runner
        if (
            timeout_seconds is not None
            and timeout_seconds != self.runner.timeout_seconds
        ):
            runner = CommandRunner(timeout_seconds=timeout_seconds)
        lock = self._alias_locks.setdefault(alias, asyncio.Lock())
        async with lock:
            return await runner.run(["ssh", alias, remote_command])


class DashboardRuntime:
    """Poll SSH targets and broadcast normalized websocket updates."""

    def __init__(
        self,
        *,
        hub: WebSocketHub,
        settings_store: DashboardSettingsStore,
        executor,
        batch_transport=None,
        metrics_stream_manager=None,
        terminal_launcher=open_terminal_with_ssh,
        stale_after_seconds: float = 15.0,
    ) -> None:
        self.hub = hub
        self.settings_store = settings_store
        self.executor = executor
        self.batch_transport = batch_transport
        self.metrics_stream_manager = metrics_stream_manager
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
        self._recent_command_health: dict[
            tuple[str, str, str], list[CommandHealthRecord]
        ] = {}
        self._failure_trackers: dict[tuple[str, str, str], FailureTracker] = {}
        self._metrics_stream_status: dict[str, _MetricsStreamStatus] = {}
        self._status_poller = StatusPoller(self)
        self._git_ops = GitOperations(self)
        self._health = CommandHealthTracker(self)
        self._cmd_exec = CommandExecutor(self)

        if self.metrics_stream_manager is not None and hasattr(
            self.metrics_stream_manager, "bind"
        ):
            self.metrics_stream_manager.bind(
                on_sample=self._handle_metrics_stream_sample,
                on_state_change=self._handle_metrics_stream_state_change,
            )

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stop_event.clear()
        if self.metrics_stream_manager is not None and hasattr(
            self.metrics_stream_manager, "start"
        ):
            await self.metrics_stream_manager.start(self.settings_store.load().servers)
        self._task = asyncio.create_task(
            self._run_loop(), name="dashboard-runtime-loop"
        )

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
        if self.metrics_stream_manager is not None and hasattr(
            self.metrics_stream_manager, "stop"
        ):
            await self.metrics_stream_manager.stop()
        if self.batch_transport is not None and hasattr(self.batch_transport, "close"):
            await self.batch_transport.close()

    async def poll_once(self) -> None:
        settings = self.settings_store.load()
        if self.metrics_stream_manager is not None and hasattr(
            self.metrics_stream_manager, "sync_servers"
        ):
            await self.metrics_stream_manager.sync_servers(settings.servers)
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
        snapshot = self._build_cached_snapshot(server_id=server.server_id, now=now)
        host_unreachable = False

        metric_results = (
            {}
            if self.metrics_stream_manager is not None
            else await self._poll_metrics(server=server)
        )

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
            elif system_execution.failure_class == "parse_error":
                self._system_last_poll_ok[server.server_id] = False
                snapshot["metadata"]["metrics_error"] = (
                    f"system parse failed: {system_execution.message}"
                )
            else:
                error_text = system_execution.message or "system failed"
                self._system_last_poll_ok[server.server_id] = False
                snapshot["metadata"]["metrics_error"] = error_text
                if system_execution.had_host_unreachable or _is_ssh_unreachable(
                    system_execution.result
                ):
                    snapshot["metadata"]["ssh_error"] = (
                        system_execution.host_unreachable_message or error_text
                    )
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
            elif gpu_execution.failure_class == "parse_error":
                self._gpu_last_poll_ok[server.server_id] = False
                snapshot["metadata"]["gpu_error"] = (
                    f"gpu parse failed: {gpu_execution.message}"
                )
            else:
                error_text = gpu_execution.message or "gpu failed"
                self._gpu_last_poll_ok[server.server_id] = False
                snapshot["metadata"]["gpu_error"] = error_text
                if gpu_execution.had_host_unreachable or _is_ssh_unreachable(
                    gpu_execution.result
                ):
                    snapshot["metadata"]["ssh_error"] = (
                        gpu_execution.host_unreachable_message or error_text
                    )
                    host_unreachable = True

        should_poll_status = _needs_status_poll(
            last=self._last_status_poll.get(server.server_id),
            now=now,
            interval_seconds=status_interval_seconds,
        )

        self._consume_finished_status_poll_task(server.server_id)

        if (
            should_poll_status
            and ("git" in enabled or "clash" in enabled)
            and not host_unreachable
        ):
            await self._start_status_poll_if_needed(server=server, now=now)
        elif should_poll_status and host_unreachable:
            if "git" in enabled:
                self._git_last_poll_ok[server.server_id] = False
            if "clash" in enabled:
                self._clash_last_poll_ok[server.server_id] = False

        await self._broadcast_server_state(
            server=server,
            now=now,
            snapshot=snapshot,
            metrics_interval_seconds=metrics_interval_seconds,
            status_interval_seconds=status_interval_seconds,
        )

    async def _handle_metrics_stream_sample(self, server_id: str, sample) -> None:
        now = datetime.now(UTC)
        system_snapshot = {
            "cpu_percent": sample.cpu_percent,
            "memory_percent": sample.memory_percent,
            "disk_percent": sample.disk_percent,
            "network_rx_kbps": sample.network_rx_kbps,
            "network_tx_kbps": sample.network_tx_kbps,
        }
        self._system_cache[server_id] = system_snapshot
        self._gpu_cache[server_id] = [dict(gpu) for gpu in sample.gpus]
        updated_at = now.isoformat()
        self._system_last_updated_at[server_id] = updated_at
        self._gpu_last_updated_at[server_id] = updated_at
        self._system_last_poll_ok[server_id] = True
        self._gpu_last_poll_ok[server_id] = True
        stream_status = self._metrics_stream_status_for(server_id)
        stream_status.state = "live"
        stream_status.last_sample_received_at = updated_at
        stream_status.last_sample_server_time = sample.server_time
        stream_status.transport_latency_ms = _metrics_stream_transport_latency_ms(
            sample_server_time=sample.server_time,
            received_at=now,
            sample_interval_ms=sample.sample_interval_ms,
        )
        stream_status.last_sequence = sample.sequence
        stream_status.sample_interval_ms = sample.sample_interval_ms
        stream_status.state_changed_at = updated_at

        server = _find_server(self.settings_store.load().servers, server_id)
        settings = self.settings_store.load()
        await self._broadcast_server_state(
            server=server,
            now=now,
            snapshot=self._build_cached_snapshot(server_id=server_id, now=now),
            metrics_interval_seconds=settings.metrics_interval_seconds,
            status_interval_seconds=settings.status_interval_seconds,
        )

    async def _handle_metrics_stream_state_change(
        self, server_id: str, state: str
    ) -> None:
        stream_status = self._metrics_stream_status_for(server_id)
        if state == "reconnecting":
            stream_status.reconnect_count += 1
        stream_status.state = state
        stream_status.state_changed_at = datetime.now(UTC).isoformat()

    def _build_cached_snapshot(self, *, server_id: str, now: datetime) -> dict:
        return self._status_poller.build_cached_snapshot(server_id=server_id, now=now)

    async def _broadcast_server_state(
        self,
        *,
        server: ServerSettings,
        now: datetime,
        snapshot: dict,
        metrics_interval_seconds: float,
        status_interval_seconds: float,
    ) -> None:
        repos = [
            repo
            for repo in self._repo_cache.get(server.server_id, [])
            if isinstance(repo, dict) and repo.get("path") in set(server.working_dirs)
        ]
        clash = dict(self._clash_cache.get(server.server_id, DEFAULT_CLASH))
        if server.server_id in self._clash_last_updated_at:
            clash["last_updated_at"] = self._clash_last_updated_at[server.server_id]

        if "git" not in server.enabled_panels:
            repos = []
        if "clash" not in server.enabled_panels:
            clash = DEFAULT_CLASH

        metrics_threshold_seconds = max(1.0, metrics_interval_seconds * 2)
        status_threshold_seconds = max(1.0, status_interval_seconds * 2)
        repo_poll_ok = self._repo_last_poll_ok.get(server.server_id, {})
        repos_with_freshness: list[dict] = []
        for repo in repos:
            normalized_repo = dict(repo)
            repo_path = normalized_repo.get("path")
            repo_last_poll_ok = (
                repo_poll_ok.get(repo_path) if isinstance(repo_path, str) else None
            )
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
                keep_live_while_inflight=self._is_status_poll_inflight(
                    server.server_id
                ),
            ),
            "clash": _build_freshness_entry(
                now=now,
                last_updated_at=self._clash_last_updated_at.get(server.server_id),
                last_poll_ok=self._clash_last_poll_ok.get(server.server_id),
                threshold_seconds=status_threshold_seconds,
                keep_live_while_inflight=self._is_status_poll_inflight(
                    server.server_id
                ),
            ),
        }

        payload = {
            "timestamp": snapshot.get("timestamp", now.isoformat()),
            "snapshot": snapshot,
            "repos": repos_with_freshness,
            "clash": clash,
            "command_health": self._summarize_server_command_health(server=server),
            "metrics_stream": self._serialize_metrics_stream_status(server.server_id),
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

    async def _poll_metrics(
        self, *, server: ServerSettings
    ) -> dict[str, _PolicyExecutionOutcome]:
        return await self._status_poller.poll_metrics(server=server)

    async def _poll_metrics_batch(
        self, *, server: ServerSettings
    ) -> dict[str, _PolicyExecutionOutcome]:
        return await self._status_poller.poll_metrics_batch(server=server)

    def _is_status_poll_inflight(self, server_id: str) -> bool:
        return self._status_poller.is_status_poll_inflight(server_id)

    def _consume_finished_status_poll_task(self, server_id: str) -> None:
        return self._status_poller.consume_finished_status_poll_task(server_id)

    def _consume_status_poll_task_result(
        self, server_id: str, task: asyncio.Task
    ) -> None:
        current = self._status_poll_tasks.get(server_id)
        if current is task:
            self._status_poll_tasks.pop(server_id, None)
        with suppress(asyncio.CancelledError):
            try:
                task.result()
            except Exception:
                self._git_last_poll_ok[server_id] = False
                self._clash_last_poll_ok[server_id] = False

    async def _start_status_poll_if_needed(
        self, *, server: ServerSettings, now: datetime
    ) -> None:
        return await self._status_poller.start_status_poll_if_needed(
            server=server, now=now
        )

    async def _poll_status_panels(
        self, *, server: ServerSettings, polled_at_iso: str
    ) -> None:
        return await self._status_poller.poll_status_panels(
            server=server, polled_at_iso=polled_at_iso
        )

    async def _poll_git_repos(
        self,
        server: ServerSettings,
        *,
        previous_repos: list[dict],
        polled_at_iso: str,
    ) -> tuple[list[dict], int, dict[str, bool]]:
        return await self._git_ops.poll_git_repos(
            server, previous_repos=previous_repos, polled_at_iso=polled_at_iso
        )

    async def _poll_single_git_repo(
        self,
        *,
        server: ServerSettings,
        repo_path: str,
        previous_repo: dict | None,
        polled_at_iso: str,
    ) -> tuple[str, dict | None, bool]:
        return await self._git_ops.poll_single_git_repo(
            server=server,
            repo_path=repo_path,
            previous_repo=previous_repo,
            polled_at_iso=polled_at_iso,
        )

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
            raise ValueError(
                f"repo '{repo_path}' is not configured for server '{server_id}'"
            )

        command = _git_operation_command(
            repo_path=repo_path, operation=operation, branch=branch
        )

        if operation == "refresh":
            operation_result = await self._run_batch_executor(
                server.ssh_alias,
                command,
                timeout_seconds=GIT_OPERATION_TIMEOUT_SECONDS,
            )
            status_result = operation_result
        else:
            operation_result = await self._run_git_operation_command(
                server.ssh_alias,
                command,
                timeout_seconds=GIT_OPERATION_TIMEOUT_SECONDS,
            )
            status_result = await self._run_batch_executor(
                server.ssh_alias,
                _git_status_command(repo_path),
                timeout_seconds=GIT_OPERATION_TIMEOUT_SECONDS,
            )

        operation_ok = operation_result.exit_code == 0 and not operation_result.error
        stderr_blob = operation_result.error or operation_result.stderr or ""
        if operation == "refresh" and status_result is not operation_result:
            stderr_blob = (
                stderr_blob or status_result.error or status_result.stderr or ""
            )

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
            raise ValueError(
                f"repo '{repo_path}' is not configured for server '{server_id}'"
            )

        launched = self.terminal_launcher(
            ssh_alias=server.ssh_alias, repo_path=repo_path
        )
        return {
            "ok": bool(getattr(launched, "ok", False)),
            "launched_with": str(getattr(launched, "launched_with", "")),
            "detail": str(getattr(launched, "detail", "")),
        }

    async def _run_executor(
        self, alias: str, remote_command: str, *, timeout_seconds: float
    ):
        try:
            return await self.executor.run(
                alias, remote_command, timeout_seconds=timeout_seconds
            )
        except TypeError:
            return await self.executor.run(alias, remote_command)

    async def _run_batch_executor(
        self, alias: str, remote_command: str, *, timeout_seconds: float
    ):
        if self.batch_transport is not None and hasattr(self.batch_transport, "run"):
            try:
                return await self.batch_transport.run(
                    alias, remote_command, timeout_seconds=timeout_seconds
                )
            except Exception:
                return await self._run_executor(
                    alias, remote_command, timeout_seconds=timeout_seconds
                )
        return await self._run_executor(
            alias, remote_command, timeout_seconds=timeout_seconds
        )

    async def _run_git_operation_command(
        self, alias: str, remote_command: str, *, timeout_seconds: float
    ):
        return await self._git_ops.run_git_operation_command(
            alias, remote_command, timeout_seconds=timeout_seconds
        )

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
        return await self._cmd_exec.execute_with_policy(
            server_id=server_id,
            ssh_alias=ssh_alias,
            command_kind=command_kind,
            target_label=target_label,
            remote_command=remote_command,
            policy=policy,
            parse_output=parse_output,
            cache_used=cache_used,
        )

    def _record_batch_failure(
        self,
        *,
        server_id: str,
        command_kind: CommandKind,
        target_label: str,
        result,
        policy: CommandPolicy,
        cache_used: bool,
    ) -> _PolicyExecutionOutcome:
        return self._cmd_exec.record_batch_failure(
            server_id=server_id,
            command_kind=command_kind,
            target_label=target_label,
            result=result,
            policy=policy,
            cache_used=cache_used,
        )

    def _record_batch_section_outcome(
        self,
        *,
        server_id: str,
        command_kind: CommandKind,
        target_label: str,
        section_group: dict[str, object] | None,
        policy: CommandPolicy,
        parse_output,
        cache_used: bool,
        fallback_duration_ms: int,
    ) -> _PolicyExecutionOutcome:
        return self._cmd_exec.record_batch_section_outcome(
            server_id=server_id,
            command_kind=command_kind,
            target_label=target_label,
            section_group=section_group,
            policy=policy,
            parse_output=parse_output,
            cache_used=cache_used,
            fallback_duration_ms=fallback_duration_ms,
        )

    def _append_command_health(self, record: CommandHealthRecord) -> None:
        return self._health.append_command_health(record)

    def _failure_tracker_for(
        self,
        *,
        server_id: str,
        command_kind: CommandKind,
        target_label: str,
        policy: CommandPolicy,
    ) -> FailureTracker:
        return self._health.failure_tracker_for(
            server_id=server_id,
            command_kind=command_kind,
            target_label=target_label,
            policy=policy,
        )

    def _summarize_server_command_health(
        self, *, server: ServerSettings
    ) -> dict[str, dict]:
        return self._health.summarize_server_command_health(server=server)

    def _summary_for_metrics_stream(self, *, server_id: str) -> dict:
        return self._health.summary_for_metrics_stream(server_id=server_id)

    def _summary_for_single_command(
        self,
        *,
        server_id: str,
        command_kind: CommandKind,
        target_label: str,
        detail: str,
    ) -> dict:
        return self._health.summary_for_single_command(
            server_id=server_id,
            command_kind=command_kind,
            target_label=target_label,
            detail=detail,
        )

    def _summary_for_git(self, *, server: ServerSettings) -> dict:
        return self._health.summary_for_git(server=server)

    def _summary_for_clash(self, *, server_id: str) -> dict:
        return self._health.summary_for_clash(server_id=server_id)

    def _latest_command_health_record(
        self,
        *,
        server_id: str,
        command_kind: CommandKind,
        target_label: str,
    ) -> CommandHealthRecord | None:
        return self._health.latest_command_health_record(
            server_id=server_id,
            command_kind=command_kind,
            target_label=target_label,
        )

    def get_recent_command_health(
        self,
        *,
        server_id: str,
        command_kind: str | None = None,
        target_label: str | None = None,
    ) -> list[dict]:
        matching: list[dict] = []
        for (
            record_server_id,
            record_command_kind,
            record_target_label,
        ), records in self._recent_command_health.items():
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

        for (server_id, command_kind, target_label), records in sorted(
            self._recent_command_health.items()
        ):
            server_entry = servers.setdefault(
                server_id, {"server_id": server_id, "commands": []}
            )
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
            avg_duration_ms = (
                int(sum(record.duration_ms for record in records) / len(records))
                if records
                else 0
            )
            last_failure_class = next(
                (record.failure_class for record in reversed(records) if not record.ok),
                "ok",
            )
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

        for server_id, stream_status in sorted(self._metrics_stream_status.items()):
            server_entry = servers.setdefault(
                server_id, {"server_id": server_id, "commands": []}
            )
            server_entry["metrics_stream"] = self._serialize_metrics_stream_status(
                server_id
            )

        return {
            "generated_at": datetime.now(UTC).isoformat(),
            "settings": _serialize_runtime_settings(settings),
            "servers": [servers[server_id] for server_id in sorted(servers.keys())],
        }

    def _metrics_stream_status_for(self, server_id: str) -> _MetricsStreamStatus:
        status = self._metrics_stream_status.get(server_id)
        if status is None:
            status = _MetricsStreamStatus()
            self._metrics_stream_status[server_id] = status
        return status

    def _serialize_metrics_stream_status(self, server_id: str) -> dict:
        stream_status = self._metrics_stream_status.get(server_id)
        if stream_status is None:
            return {}
        return {
            "state": stream_status.state,
            "last_sample_received_at": stream_status.last_sample_received_at,
            "last_sample_server_time": stream_status.last_sample_server_time,
            "transport_latency_ms": stream_status.transport_latency_ms,
            "last_sequence": stream_status.last_sequence,
            "sample_interval_ms": stream_status.sample_interval_ms,
            "reconnect_count": stream_status.reconnect_count,
            "state_changed_at": stream_status.state_changed_at,
        }

    def _replace_cached_repo(self, *, server_id: str, repo: dict) -> None:
        return self._git_ops.replace_cached_repo(server_id=server_id, repo=repo)
