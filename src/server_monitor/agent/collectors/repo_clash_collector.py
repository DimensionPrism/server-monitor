"""Collector for repository and Clash status."""

from __future__ import annotations

from datetime import UTC, datetime

from server_monitor.agent.parsers.clash import parse_clash_status
from server_monitor.agent.parsers.git_status import parse_repo_status
from server_monitor.agent.snapshot_store import SnapshotStore


class RepoClashCollector:
    """Collect slower-changing repository and proxy status."""

    def __init__(
        self,
        *,
        runner,
        store: SnapshotStore,
        repo_paths: list[str],
        git_status_cmd: list[str],
        clash_status_cmd: list[str],
    ) -> None:
        self.runner = runner
        self.store = store
        self.repo_paths = repo_paths
        self.git_status_cmd = git_status_cmd
        self.clash_status_cmd = clash_status_cmd

    async def collect_once(self, *, now: datetime | None = None) -> None:
        timestamp = now or datetime.now(UTC)
        repos: list[dict] = []
        for repo_path in self.repo_paths:
            result = await self.runner.run([*self.git_status_cmd, repo_path])
            if result.exit_code != 0 or result.error:
                continue
            repos.append(
                parse_repo_status(
                    path=repo_path,
                    porcelain_text=result.stdout,
                    last_commit_age_seconds=0,
                )
            )

        if repos:
            self.store.update_repos(repos, timestamp=timestamp)

        clash_result = await self.runner.run(self.clash_status_cmd)
        if clash_result.exit_code == 0 and not clash_result.error:
            self.store.update_clash(parse_clash_status(clash_result.stdout), timestamp=timestamp)

