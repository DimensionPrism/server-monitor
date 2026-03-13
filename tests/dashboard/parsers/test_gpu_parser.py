from pathlib import Path

import pytest


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


def test_parse_nvidia_smi_jetson_na_values_defaults_to_zero():
    from server_monitor.dashboard.parsers.gpu import parse_gpu_snapshot

    parsed = parse_gpu_snapshot("0, Orin (nvgpu), [N/A], [N/A], [N/A], [N/A]")

    assert parsed == [
        {
            "index": 0,
            "name": "Orin (nvgpu)",
            "utilization_gpu": 0.0,
            "memory_used_mb": 0.0,
            "memory_total_mb": 0.0,
            "temperature_c": 0.0,
            "processes": [],
        }
    ]


def test_parse_nvidia_smi_unexpected_non_numeric_value_raises():
    from server_monitor.dashboard.parsers.gpu import parse_gpu_snapshot

    with pytest.raises(ValueError):
        parse_gpu_snapshot("0, Orin (nvgpu), bad-value, 123, 456, 50")
