from pathlib import Path


PROJECT_ROOT = Path(__file__).parents[2]
LEGACY_AGENT_NAMESPACE = "server_monitor." + "agent"
LEGACY_SHARED_NAMESPACE = "server_monitor." + "shared"


def test_source_tree_has_no_legacy_agent_or_shared_imports():
    source_root = PROJECT_ROOT / "src" / "server_monitor"
    offenders: list[str] = []

    for path in source_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="replace")
        if LEGACY_AGENT_NAMESPACE in text or LEGACY_SHARED_NAMESPACE in text:
            offenders.append(path.relative_to(PROJECT_ROOT).as_posix())

    assert offenders == []


def test_dashboard_http_agent_compatibility_files_are_removed():
    assert not (PROJECT_ROOT / "src/server_monitor/dashboard/poller.py").exists()
    assert not (PROJECT_ROOT / "src/server_monitor/dashboard/config.py").exists()
