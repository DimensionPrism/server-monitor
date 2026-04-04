from pathlib import Path


def _load(name: str) -> str:
    return (Path(__file__).parents[2] / "fixtures" / "outputs" / name).read_text()


def test_parse_system_snapshot_fixture():
    from server_monitor.dashboard.panels.parsers.system import parse_system_snapshot

    parsed = parse_system_snapshot(_load("system_snapshot.txt"))

    assert parsed["cpu_percent"] == 23.5
    assert parsed["memory_percent"] == 47.0
    assert parsed["disk_percent"] == 65.2
    assert parsed["network_rx_kbps"] == 120.3
    assert parsed["network_tx_kbps"] == 78.1
