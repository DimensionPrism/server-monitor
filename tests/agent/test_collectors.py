from dataclasses import dataclass
from datetime import UTC, datetime

import pytest


@dataclass
class _FakeResult:
    stdout: str
    stderr: str = ""
    exit_code: int = 0
    duration_ms: int = 1
    error: str | None = None


class _FakeRunner:
    def __init__(self, mapping):
        self.mapping = mapping

    async def run(self, argv):
        key = " ".join(argv)
        return self.mapping[key]


@pytest.mark.asyncio
async def test_metrics_collector_updates_store_when_commands_succeed():
    from server_monitor.agent.collectors.metrics_collector import MetricsCollector
    from server_monitor.agent.snapshot_store import SnapshotStore

    store = SnapshotStore(server_id="server-a")
    runner = _FakeRunner(
        {
            "collect-system": _FakeResult("CPU: 11.0\nMEM: 22.0\nDISK: 33.0\nRX_KBPS: 44.0\nTX_KBPS: 55.0"),
            "collect-gpu": _FakeResult("0, NVIDIA A100, 70, 1024, 40960, 50"),
        }
    )

    collector = MetricsCollector(
        runner=runner,
        store=store,
        system_cmd=["collect-system"],
        gpu_cmd=["collect-gpu"],
    )

    await collector.collect_once(now=datetime(2026, 3, 10, tzinfo=UTC))

    snapshot = store.snapshot
    assert snapshot.cpu_percent == 11.0
    assert len(snapshot.gpus) == 1


@pytest.mark.asyncio
async def test_repo_clash_collector_keeps_previous_repo_on_git_failure():
    from server_monitor.agent.collectors.repo_clash_collector import RepoClashCollector
    from server_monitor.agent.snapshot_store import SnapshotStore

    store = SnapshotStore(server_id="server-a")
    store.update_repos(
        [
            {
                "path": "/work/repo",
                "branch": "main",
                "dirty": False,
                "ahead": 0,
                "behind": 0,
                "staged": 0,
                "unstaged": 0,
                "untracked": 0,
                "last_commit_age_seconds": 120,
            }
        ],
        timestamp=datetime(2026, 3, 10, tzinfo=UTC),
    )

    runner = _FakeRunner(
        {
            "git-status /work/repo": _FakeResult("", exit_code=1, stderr="failed"),
            "clash-status": _FakeResult("running=true\napi_reachable=true\nui_reachable=false\nmessage=ok"),
        }
    )

    collector = RepoClashCollector(
        runner=runner,
        store=store,
        repo_paths=["/work/repo"],
        git_status_cmd=["git-status"],
        clash_status_cmd=["clash-status"],
    )

    await collector.collect_once(now=datetime(2026, 3, 10, tzinfo=UTC))

    snapshot = store.snapshot
    assert snapshot.repos[0].path == "/work/repo"
    assert snapshot.clash.running is True
