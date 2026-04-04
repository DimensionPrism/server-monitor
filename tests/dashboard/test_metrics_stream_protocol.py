import pytest


def test_parse_metrics_stream_line_returns_typed_sample():
    from server_monitor.dashboard.metrics.protocol import (
        MetricsStreamSample,
        parse_metrics_stream_line,
    )

    line = (
        '{"sequence":7,"server_time":"2026-03-12T12:00:00+00:00","sample_interval_ms":250,'
        '"cpu_percent":11.0,"memory_percent":22.0,"disk_percent":33.0,'
        '"network_rx_kbps":44.0,"network_tx_kbps":55.0,'
        '"gpus":[{"index":0,"name":"NVIDIA A100","utilization_gpu_percent":70.0,'
        '"memory_used_mib":1024,"memory_total_mib":40960,"temperature_celsius":50.0}]}'
    )

    sample = parse_metrics_stream_line(line)

    assert sample == MetricsStreamSample(
        sequence=7,
        server_time="2026-03-12T12:00:00+00:00",
        sample_interval_ms=250,
        cpu_percent=11.0,
        memory_percent=22.0,
        disk_percent=33.0,
        network_rx_kbps=44.0,
        network_tx_kbps=55.0,
        gpus=[
            {
                "index": 0,
                "name": "NVIDIA A100",
                "utilization_gpu_percent": 70.0,
                "memory_used_mib": 1024,
                "memory_total_mib": 40960,
                "temperature_celsius": 50.0,
            }
        ],
    )


def test_parse_metrics_stream_line_rejects_malformed_json():
    from server_monitor.dashboard.metrics.protocol import (
        MetricsStreamProtocolError,
        parse_metrics_stream_line,
    )

    with pytest.raises(MetricsStreamProtocolError, match="malformed JSON"):
        parse_metrics_stream_line('{"sequence":1')


def test_parse_metrics_stream_line_rejects_missing_required_field():
    from server_monitor.dashboard.metrics.protocol import (
        MetricsStreamProtocolError,
        parse_metrics_stream_line,
    )

    line = (
        '{"server_time":"2026-03-12T12:00:00+00:00","sample_interval_ms":250,'
        '"cpu_percent":11.0,"memory_percent":22.0,"disk_percent":33.0,'
        '"network_rx_kbps":44.0,"network_tx_kbps":55.0,"gpus":[]}'
    )

    with pytest.raises(
        MetricsStreamProtocolError, match="missing required field 'sequence'"
    ):
        parse_metrics_stream_line(line)
