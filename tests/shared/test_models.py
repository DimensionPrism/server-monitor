import pytest


def test_snapshot_requires_server_id():
    from server_monitor.shared.models import ServerSnapshot

    with pytest.raises(Exception):
        ServerSnapshot.model_validate({"timestamp": "2026-03-10T00:00:00Z"})


def test_snapshot_minimal_passes():
    from server_monitor.shared.models import ClashStatus, RepoStatus, ServerSnapshot

    data = {
        "server_id": "server-a",
        "timestamp": "2026-03-10T00:00:00Z",
        "cpu_percent": 12.5,
        "memory_percent": 34.2,
        "disk_percent": 45.0,
        "network_rx_kbps": 100.0,
        "network_tx_kbps": 50.0,
        "gpus": [],
        "repos": [
            RepoStatus(
                path="/work/repo",
                branch="main",
                dirty=False,
                ahead=0,
                behind=0,
                staged=0,
                unstaged=0,
                untracked=0,
                last_commit_age_seconds=120,
            ).model_dump()
        ],
        "clash": ClashStatus(
            running=True,
            api_reachable=True,
            ui_reachable=False,
            message="ok",
        ).model_dump(),
    }

    parsed = ServerSnapshot.model_validate(data)
    assert parsed.server_id == "server-a"
