from dataclasses import dataclass
from datetime import UTC, datetime

import pytest


@dataclass
class _Result:
    stdout: str
    stderr: str = ""
    exit_code: int = 0
    duration_ms: int = 1
    error: str | None = None


class _Runner:
    def __init__(self):
        self.calls = []

    async def run(self, argv):
        self.calls.append(argv)
        joined = " ".join(argv)
        if "git" in joined:
            return _Result("## main...origin/main\n")
        return _Result("running=true\napi_reachable=false\nui_reachable=false\nmessage=ok")


@pytest.mark.asyncio
async def test_repo_collector_supports_repo_placeholder():
    from server_monitor.agent.collectors.repo_clash_collector import RepoClashCollector
    from server_monitor.agent.snapshot_store import SnapshotStore

    runner = _Runner()
    collector = RepoClashCollector(
        runner=runner,
        store=SnapshotStore(server_id="server-a"),
        repo_paths=["/work/repo"],
        git_status_cmd=["git", "-C", "{repo}", "status", "--porcelain", "--branch"],
        clash_status_cmd=["echo", "running=true"],
    )

    await collector.collect_once(now=datetime(2026, 3, 10, tzinfo=UTC))

    assert runner.calls[0] == ["git", "-C", "/work/repo", "status", "--porcelain", "--branch"]
