"""Git operations extracted from runtime.py."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from server_monitor.dashboard.runtime import DashboardRuntime

from server_monitor.dashboard.health.command_policy import CommandKind
from server_monitor.dashboard.parsers.git_status import parse_repo_status
from server_monitor.dashboard.runtime.runtime_helpers import (
    _git_status_command,
)


class GitOperations:
    def __init__(self, runtime: "DashboardRuntime") -> None:
        self._runtime = runtime

    async def poll_git_repos(
        self,
        server,
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
                self.poll_single_git_repo(
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

    async def poll_single_git_repo(
        self,
        *,
        server,
        repo_path: str,
        previous_repo: dict | None,
        polled_at_iso: str,
    ) -> tuple[str, dict | None, bool]:
        command = _git_status_command(repo_path)
        execution = await self._runtime._execute_with_policy(
            server_id=server.server_id,
            ssh_alias=server.ssh_alias,
            command_kind=CommandKind.GIT_STATUS,
            target_label=repo_path,
            remote_command=command,
            policy=self._runtime._command_policies[CommandKind.GIT_STATUS],
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

    async def run_git_operation_command(
        self, alias: str, remote_command: str, *, timeout_seconds: float
    ):
        if self._runtime.batch_transport is not None and hasattr(
            self._runtime.batch_transport, "run"
        ):
            try:
                return await self._runtime.batch_transport.run(
                    alias, remote_command, timeout_seconds=timeout_seconds
                )
            except Exception as exc:
                message = str(exc) or "persistent transport failed"
                return SimpleNamespace(
                    stdout="",
                    stderr=message,
                    exit_code=-1,
                    duration_ms=0,
                    error=message,
                )
        return await self._runtime._run_executor(
            alias, remote_command, timeout_seconds=timeout_seconds
        )

    def replace_cached_repo(self, *, server_id: str, repo: dict) -> None:
        existing = self._runtime._repo_cache.get(server_id, [])
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
        self._runtime._repo_cache[server_id] = updated
