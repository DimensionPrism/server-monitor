"""Status polling logic extracted from runtime.py."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import datetime
from types import SimpleNamespace
from typing import TYPE_CHECKING

from server_monitor.dashboard.batch_protocol import (
    BatchProtocolError,
    build_metrics_batch_command,
    build_status_batch_command,
    parse_batch_output,
)
from server_monitor.dashboard.command_policy import CommandKind
from server_monitor.dashboard.parsers.clash import parse_clash_status
from server_monitor.dashboard.parsers.git_status import parse_repo_status
from server_monitor.dashboard.parsers.gpu import parse_gpu_snapshot
from server_monitor.dashboard.parsers.system import parse_system_snapshot
from server_monitor.dashboard.runtime_helpers import (
    DEFAULT_CLASH,
    STATUS_POLL_INLINE_BUDGET_SECONDS,
    _batched_clash_secret_command,
    _batched_clash_probe_command,
    _clash_command,
    _clash_secret_command,
    _git_status_command,
    _gpu_command,
    _group_batch_sections,
    _parse_required_clash_secret,
    _system_command,
)

if TYPE_CHECKING:
    from server_monitor.dashboard.runtime import _PolicyExecutionOutcome


class StatusPoller:
    def __init__(self, runtime) -> None:
        self._runtime = runtime

    def is_status_poll_inflight(self, server_id: str) -> bool:
        task = self._runtime._status_poll_tasks.get(server_id)
        return task is not None and not task.done()

    def consume_finished_status_poll_task(self, server_id: str) -> None:
        task = self._runtime._status_poll_tasks.get(server_id)
        if task is None or not task.done():
            return
        self._runtime._consume_status_poll_task_result(server_id, task)

    def _consume_status_poll_task_result(
        self, server_id: str, task: asyncio.Task
    ) -> None:
        current = self._runtime._status_poll_tasks.get(server_id)
        if current is task:
            self._runtime._status_poll_tasks.pop(server_id, None)
        with suppress(asyncio.CancelledError):
            try:
                task.result()
            except Exception:
                self._runtime._git_last_poll_ok[server_id] = False
                self._runtime._clash_last_poll_ok[server_id] = False

    async def start_status_poll_if_needed(self, *, server, now: datetime) -> None:
        existing = self._runtime._status_poll_tasks.get(server.server_id)
        if existing is not None:
            if existing.done():
                self._runtime._consume_status_poll_task_result(
                    server.server_id, existing
                )
            else:
                return

        poll_task = asyncio.create_task(
            self._runtime._poll_status_panels(
                server=server, polled_at_iso=now.isoformat()
            ),
            name=f"dashboard-status-poll-{server.server_id}",
        )
        self._runtime._status_poll_tasks[server.server_id] = poll_task
        self._runtime._last_status_poll[server.server_id] = now

        try:
            await asyncio.wait_for(
                asyncio.shield(poll_task), timeout=STATUS_POLL_INLINE_BUDGET_SECONDS
            )
        except asyncio.TimeoutError:
            return
        finally:
            self._runtime._consume_finished_status_poll_task(server.server_id)

    async def poll_status_panels(self, *, server, polled_at_iso: str) -> None:
        enabled = set(server.enabled_panels)
        allowed_paths = set(server.working_dirs)
        previous_repos = [
            repo
            for repo in self._runtime._repo_cache.get(server.server_id, [])
            if repo.get("path") in allowed_paths
        ]
        if not ("git" in enabled and "clash" in enabled):
            status_tasks: dict[str, asyncio.Task] = {}

            if "git" in enabled:
                status_tasks["git"] = asyncio.create_task(
                    self._runtime._poll_git_repos(
                        server,
                        previous_repos=previous_repos,
                        polled_at_iso=polled_at_iso,
                    )
                )

            if "clash" in enabled:
                secret_execution = await self._runtime._execute_with_policy(
                    server_id=server.server_id,
                    ssh_alias=server.ssh_alias,
                    command_kind=CommandKind.CLASH_SECRET,
                    target_label="server",
                    remote_command=_clash_secret_command(),
                    policy=self._runtime._command_policies[CommandKind.CLASH_SECRET],
                    parse_output=_parse_required_clash_secret,
                    cache_used=server.server_id in self._runtime._clash_cache,
                )
                if secret_execution.failure_class == "ok":
                    status_tasks["clash"] = asyncio.create_task(
                        self._runtime._execute_with_policy(
                            server_id=server.server_id,
                            ssh_alias=server.ssh_alias,
                            command_kind=CommandKind.CLASH_PROBE,
                            target_label="server",
                            remote_command=_clash_command(
                                api_probe_url=server.clash_api_probe_url,
                                ui_probe_url=server.clash_ui_probe_url,
                                secret=secret_execution.parsed,
                            ),
                            policy=self._runtime._command_policies[
                                CommandKind.CLASH_PROBE
                            ],
                            parse_output=parse_clash_status,
                            cache_used=server.server_id in self._runtime._clash_cache,
                        )
                    )
                elif (
                    secret_execution.failure_class == "parse_error"
                    and secret_execution.message == "secret-unavailable"
                ):
                    clash = dict(
                        self._runtime._clash_cache.get(server.server_id, DEFAULT_CLASH)
                    )
                    clash["api_reachable"] = False
                    clash["ui_reachable"] = False
                    clash["message"] = "secret-unavailable"
                    clash["last_updated_at"] = polled_at_iso
                    self._runtime._clash_cache[server.server_id] = clash
                    self._runtime._clash_last_updated_at[server.server_id] = (
                        polled_at_iso
                    )
                    self._runtime._clash_last_poll_ok[server.server_id] = False
                else:
                    self._runtime._clash_last_poll_ok[server.server_id] = False

            status_results: dict[str, object] = {}
            if status_tasks:
                gathered = await asyncio.gather(
                    *status_tasks.values(), return_exceptions=True
                )
                for key, result in zip(status_tasks.keys(), gathered):
                    status_results[key] = result

            if "git" in status_results:
                git_result = status_results["git"]
                if isinstance(git_result, Exception):
                    self._runtime._git_last_poll_ok[server.server_id] = False
                else:
                    polled_repos, successful_polls, repo_poll_ok = git_result
                    total_repos = len(server.working_dirs)
                    self._runtime._git_last_poll_ok[server.server_id] = (
                        successful_polls == total_repos
                    )
                    self._runtime._repo_last_poll_ok[server.server_id] = repo_poll_ok
                    if successful_polls > 0 or len(previous_repos) == 0:
                        self._runtime._repo_cache[server.server_id] = polled_repos
                        self._runtime._git_last_updated_at[server.server_id] = (
                            polled_at_iso
                        )

            if "clash" in status_results:
                clash_execution = status_results["clash"]
                if isinstance(clash_execution, Exception):
                    self._runtime._clash_last_poll_ok[server.server_id] = False
                elif clash_execution.failure_class == "ok":
                    clash = clash_execution.parsed
                    clash["last_updated_at"] = polled_at_iso
                    self._runtime._clash_cache[server.server_id] = clash
                    self._runtime._clash_last_updated_at[server.server_id] = (
                        polled_at_iso
                    )
                    self._runtime._clash_last_poll_ok[server.server_id] = True
                else:
                    self._runtime._clash_last_poll_ok[server.server_id] = False
            return

        previous_by_path = {
            repo.get("path"): repo
            for repo in previous_repos
            if isinstance(repo, dict) and isinstance(repo.get("path"), str)
        }

        git_commands = (
            [
                (repo_path, _git_status_command(repo_path))
                for repo_path in server.working_dirs
            ]
            if "git" in enabled
            else []
        )
        batch_command = build_status_batch_command(
            token="SMTOKEN",
            git_commands=git_commands,
            clash_secret_command=_batched_clash_secret_command()
            if "clash" in enabled
            else "true",
            clash_probe_command=(
                _batched_clash_probe_command(
                    api_probe_url=server.clash_api_probe_url,
                    ui_probe_url=server.clash_ui_probe_url,
                )
                if "clash" in enabled
                else "true"
            ),
        )
        batch_timeout_seconds = max(
            self._runtime._command_policies[CommandKind.GIT_STATUS].timeout_seconds
            if "git" in enabled
            else 0.0,
            self._runtime._command_policies[CommandKind.CLASH_SECRET].timeout_seconds
            if "clash" in enabled
            else 0.0,
            self._runtime._command_policies[CommandKind.CLASH_PROBE].timeout_seconds
            if "clash" in enabled
            else 0.0,
        )
        batch_result = await self._runtime._run_batch_executor(
            server.ssh_alias,
            batch_command,
            timeout_seconds=batch_timeout_seconds,
        )
        batch_duration_ms = int(getattr(batch_result, "duration_ms", 0))

        if batch_result.exit_code != 0 and not batch_result.stdout:
            if "git" in enabled:
                self._runtime._git_last_poll_ok[server.server_id] = False
                self._runtime._repo_last_poll_ok[server.server_id] = {
                    repo_path: False for repo_path in server.working_dirs
                }
                for repo_path in server.working_dirs:
                    self._runtime._record_batch_failure(
                        server_id=server.server_id,
                        command_kind=CommandKind.GIT_STATUS,
                        target_label=repo_path,
                        result=batch_result,
                        policy=self._runtime._command_policies[CommandKind.GIT_STATUS],
                        cache_used=previous_by_path.get(repo_path) is not None,
                    )
            if "clash" in enabled:
                self._runtime._clash_last_poll_ok[server.server_id] = False
                self._runtime._record_batch_failure(
                    server_id=server.server_id,
                    command_kind=CommandKind.CLASH_SECRET,
                    target_label="server",
                    result=batch_result,
                    policy=self._runtime._command_policies[CommandKind.CLASH_SECRET],
                    cache_used=server.server_id in self._runtime._clash_cache,
                )
                self._runtime._record_batch_failure(
                    server_id=server.server_id,
                    command_kind=CommandKind.CLASH_PROBE,
                    target_label="server",
                    result=batch_result,
                    policy=self._runtime._command_policies[CommandKind.CLASH_PROBE],
                    cache_used=server.server_id in self._runtime._clash_cache,
                )
            return

        try:
            sections = parse_batch_output(batch_result.stdout, token="SMTOKEN")
        except BatchProtocolError as exc:
            malformed_result = SimpleNamespace(
                stdout=batch_result.stdout,
                stderr=str(exc),
                exit_code=-1,
                duration_ms=batch_duration_ms,
                error="parse_error",
            )
            if "git" in enabled:
                self._runtime._git_last_poll_ok[server.server_id] = False
                self._runtime._repo_last_poll_ok[server.server_id] = {
                    repo_path: False for repo_path in server.working_dirs
                }
                for repo_path in server.working_dirs:
                    self._runtime._record_batch_failure(
                        server_id=server.server_id,
                        command_kind=CommandKind.GIT_STATUS,
                        target_label=repo_path,
                        result=malformed_result,
                        policy=self._runtime._command_policies[CommandKind.GIT_STATUS],
                        cache_used=previous_by_path.get(repo_path) is not None,
                    )
            if "clash" in enabled:
                self._runtime._clash_last_poll_ok[server.server_id] = False
                self._runtime._record_batch_failure(
                    server_id=server.server_id,
                    command_kind=CommandKind.CLASH_SECRET,
                    target_label="server",
                    result=malformed_result,
                    policy=self._runtime._command_policies[CommandKind.CLASH_SECRET],
                    cache_used=server.server_id in self._runtime._clash_cache,
                )
                self._runtime._record_batch_failure(
                    server_id=server.server_id,
                    command_kind=CommandKind.CLASH_PROBE,
                    target_label="server",
                    result=malformed_result,
                    policy=self._runtime._command_policies[CommandKind.CLASH_PROBE],
                    cache_used=server.server_id in self._runtime._clash_cache,
                )
            return

        grouped_sections = _group_batch_sections(sections)

        if "git" in enabled:
            repos: list[dict] = []
            successful_polls = 0
            repo_poll_ok: dict[str, bool] = {}
            for repo_path in server.working_dirs:
                execution = self._runtime._record_batch_section_outcome(
                    server_id=server.server_id,
                    command_kind=CommandKind.GIT_STATUS,
                    target_label=repo_path,
                    section_group=grouped_sections.get(("git_status", repo_path)),
                    policy=self._runtime._command_policies[CommandKind.GIT_STATUS],
                    parse_output=lambda stdout, repo_path=repo_path: parse_repo_status(
                        path=repo_path,
                        porcelain_text=stdout,
                        last_commit_age_seconds=0,
                    ),
                    cache_used=previous_by_path.get(repo_path) is not None,
                    fallback_duration_ms=batch_duration_ms,
                )
                success = execution.failure_class == "ok"
                repo_poll_ok[repo_path] = success
                if success:
                    repo = execution.parsed
                    repo["last_updated_at"] = polled_at_iso
                    repos.append(repo)
                    successful_polls += 1
                elif previous_repo := previous_by_path.get(repo_path):
                    repos.append(previous_repo)
            self._runtime._git_last_poll_ok[server.server_id] = successful_polls == len(
                server.working_dirs
            )
            self._runtime._repo_last_poll_ok[server.server_id] = repo_poll_ok
            if successful_polls > 0 or len(previous_repos) == 0:
                self._runtime._repo_cache[server.server_id] = repos
                self._runtime._git_last_updated_at[server.server_id] = polled_at_iso

        if "clash" in enabled:
            secret_execution = self._runtime._record_batch_section_outcome(
                server_id=server.server_id,
                command_kind=CommandKind.CLASH_SECRET,
                target_label="server",
                section_group=grouped_sections.get(("clash_secret", "server")),
                policy=self._runtime._command_policies[CommandKind.CLASH_SECRET],
                parse_output=_parse_required_clash_secret,
                cache_used=server.server_id in self._runtime._clash_cache,
                fallback_duration_ms=batch_duration_ms,
            )
            if secret_execution.failure_class == "ok":
                clash_execution = self._runtime._record_batch_section_outcome(
                    server_id=server.server_id,
                    command_kind=CommandKind.CLASH_PROBE,
                    target_label="server",
                    section_group=grouped_sections.get(("clash_probe", "server")),
                    policy=self._runtime._command_policies[CommandKind.CLASH_PROBE],
                    parse_output=parse_clash_status,
                    cache_used=server.server_id in self._runtime._clash_cache,
                    fallback_duration_ms=batch_duration_ms,
                )
                if clash_execution.failure_class == "ok":
                    clash = clash_execution.parsed
                    clash["last_updated_at"] = polled_at_iso
                    self._runtime._clash_cache[server.server_id] = clash
                    self._runtime._clash_last_updated_at[server.server_id] = (
                        polled_at_iso
                    )
                    self._runtime._clash_last_poll_ok[server.server_id] = True
                else:
                    self._runtime._clash_last_poll_ok[server.server_id] = False
            elif (
                secret_execution.failure_class == "parse_error"
                and secret_execution.message == "secret-unavailable"
            ):
                clash = dict(
                    self._runtime._clash_cache.get(server.server_id, DEFAULT_CLASH)
                )
                clash["api_reachable"] = False
                clash["ui_reachable"] = False
                clash["message"] = "secret-unavailable"
                clash["last_updated_at"] = polled_at_iso
                self._runtime._clash_cache[server.server_id] = clash
                self._runtime._clash_last_updated_at[server.server_id] = polled_at_iso
                self._runtime._clash_last_poll_ok[server.server_id] = False
            else:
                self._runtime._clash_last_poll_ok[server.server_id] = False

    async def poll_metrics(self, *, server) -> dict[str, _PolicyExecutionOutcome]:
        enabled = set(server.enabled_panels)
        if "system" in enabled and "gpu" in enabled:
            return await self._runtime._poll_metrics_batch(server=server)

        metric_tasks: dict[str, asyncio.Task] = {}
        if "system" in enabled:
            metric_tasks["system"] = asyncio.create_task(
                self._runtime._execute_with_policy(
                    server_id=server.server_id,
                    ssh_alias=server.ssh_alias,
                    command_kind=CommandKind.SYSTEM,
                    target_label="server",
                    remote_command=_system_command(),
                    policy=self._runtime._command_policies[CommandKind.SYSTEM],
                    parse_output=parse_system_snapshot,
                    cache_used=server.server_id in self._runtime._system_cache,
                )
            )
        if "gpu" in enabled:
            metric_tasks["gpu"] = asyncio.create_task(
                self._runtime._execute_with_policy(
                    server_id=server.server_id,
                    ssh_alias=server.ssh_alias,
                    command_kind=CommandKind.GPU,
                    target_label="server",
                    remote_command=_gpu_command(),
                    policy=self._runtime._command_policies[CommandKind.GPU],
                    parse_output=parse_gpu_snapshot,
                    cache_used=server.server_id in self._runtime._gpu_cache,
                )
            )

        metric_results: dict[str, _PolicyExecutionOutcome] = {}
        if metric_tasks:
            gathered = await asyncio.gather(*metric_tasks.values())
            for key, result in zip(metric_tasks.keys(), gathered):
                metric_results[key] = result
        return metric_results

    async def poll_metrics_batch(self, *, server) -> dict[str, _PolicyExecutionOutcome]:
        token = "SMTOKEN"
        batch_timeout_seconds = max(
            self._runtime._command_policies[CommandKind.SYSTEM].timeout_seconds,
            self._runtime._command_policies[CommandKind.GPU].timeout_seconds,
        )
        batch_command = build_metrics_batch_command(
            token=token,
            system_command=_system_command(),
            gpu_command=_gpu_command(),
        )
        batch_result = await self._runtime._run_batch_executor(
            server.ssh_alias,
            batch_command,
            timeout_seconds=batch_timeout_seconds,
        )
        batch_duration_ms = int(getattr(batch_result, "duration_ms", 0))

        if batch_result.exit_code != 0 and not batch_result.stdout:
            return {
                "system": self._runtime._record_batch_failure(
                    server_id=server.server_id,
                    command_kind=CommandKind.SYSTEM,
                    target_label="server",
                    result=batch_result,
                    policy=self._runtime._command_policies[CommandKind.SYSTEM],
                    cache_used=server.server_id in self._runtime._system_cache,
                ),
                "gpu": self._runtime._record_batch_failure(
                    server_id=server.server_id,
                    command_kind=CommandKind.GPU,
                    target_label="server",
                    result=batch_result,
                    policy=self._runtime._command_policies[CommandKind.GPU],
                    cache_used=server.server_id in self._runtime._gpu_cache,
                ),
            }

        try:
            sections = parse_batch_output(batch_result.stdout, token=token)
        except BatchProtocolError as exc:
            malformed_result = SimpleNamespace(
                stdout=batch_result.stdout,
                stderr=str(exc),
                exit_code=-1,
                duration_ms=batch_duration_ms,
                error="parse_error",
            )
            return {
                "system": self._runtime._record_batch_failure(
                    server_id=server.server_id,
                    command_kind=CommandKind.SYSTEM,
                    target_label="server",
                    result=malformed_result,
                    policy=self._runtime._command_policies[CommandKind.SYSTEM],
                    cache_used=server.server_id in self._runtime._system_cache,
                ),
                "gpu": self._runtime._record_batch_failure(
                    server_id=server.server_id,
                    command_kind=CommandKind.GPU,
                    target_label="server",
                    result=malformed_result,
                    policy=self._runtime._command_policies[CommandKind.GPU],
                    cache_used=server.server_id in self._runtime._gpu_cache,
                ),
            }

        grouped_sections = _group_batch_sections(sections)
        return {
            "system": self._runtime._record_batch_section_outcome(
                server_id=server.server_id,
                command_kind=CommandKind.SYSTEM,
                target_label="server",
                section_group=grouped_sections.get(("system", "server")),
                policy=self._runtime._command_policies[CommandKind.SYSTEM],
                parse_output=parse_system_snapshot,
                cache_used=server.server_id in self._runtime._system_cache,
                fallback_duration_ms=batch_duration_ms,
            ),
            "gpu": self._runtime._record_batch_section_outcome(
                server_id=server.server_id,
                command_kind=CommandKind.GPU,
                target_label="server",
                section_group=grouped_sections.get(("gpu", "server")),
                policy=self._runtime._command_policies[CommandKind.GPU],
                parse_output=parse_gpu_snapshot,
                cache_used=server.server_id in self._runtime._gpu_cache,
                fallback_duration_ms=batch_duration_ms,
            ),
        }

    def build_cached_snapshot(self, *, server_id: str, now: datetime) -> dict:
        from server_monitor.dashboard.runtime_helpers import _empty_system_snapshot

        cached_system = self._runtime._system_cache.get(
            server_id, _empty_system_snapshot()
        )
        cached_gpus = self._runtime._gpu_cache.get(server_id, [])
        metadata: dict[str, str] = {}
        if server_id in self._runtime._system_last_updated_at:
            metadata["system_last_updated_at"] = self._runtime._system_last_updated_at[
                server_id
            ]
        if server_id in self._runtime._gpu_last_updated_at:
            metadata["gpu_last_updated_at"] = self._runtime._gpu_last_updated_at[
                server_id
            ]
        return {
            "timestamp": now.isoformat(),
            "cpu_percent": cached_system["cpu_percent"],
            "memory_percent": cached_system["memory_percent"],
            "disk_percent": cached_system["disk_percent"],
            "network_rx_kbps": cached_system["network_rx_kbps"],
            "network_tx_kbps": cached_system["network_tx_kbps"],
            "gpus": [dict(gpu) for gpu in cached_gpus],
            "metadata": metadata,
        }
