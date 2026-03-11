from pathlib import Path


def _load(name: str) -> str:
    return (Path(__file__).parents[2] / "fixtures" / "outputs" / name).read_text()


def test_parse_nvidia_smi_fixture():
    from server_monitor.dashboard.parsers.gpu import parse_gpu_snapshot

    parsed = parse_gpu_snapshot(_load("nvidia_smi_query.txt"))

    assert len(parsed) == 2
    assert parsed[0]["index"] == 0
    assert parsed[0]["utilization_gpu"] == 73
    assert parsed[0]["memory_used_mb"] == 20480
    assert parsed[0]["temperature_c"] == 61
