def test_build_metrics_stream_command_contains_sampling_loop():
    from server_monitor.dashboard.metrics_stream_command import build_metrics_stream_command

    command = build_metrics_stream_command(sample_interval_seconds=0.25, disk_interval_seconds=5.0)

    assert "while :" in command
    assert "sleep 0.25" in command


def test_build_metrics_stream_command_reads_proc_net_dev_for_network_deltas():
    from server_monitor.dashboard.metrics_stream_command import build_metrics_stream_command

    command = build_metrics_stream_command(sample_interval_seconds=0.25, disk_interval_seconds=5.0)

    assert "/proc/net/dev" in command
    assert "PREV_RX_BYTES" in command
    assert "PREV_TX_BYTES" in command


def test_build_metrics_stream_command_refreshes_disk_less_often_than_every_sample():
    from server_monitor.dashboard.metrics_stream_command import build_metrics_stream_command

    command = build_metrics_stream_command(sample_interval_seconds=0.25, disk_interval_seconds=5.0)

    assert "DISK_REFRESH_TICKS=20" in command
    assert "DISK_TICK=0" in command


def test_build_metrics_stream_command_queries_gpu_every_sample():
    from server_monitor.dashboard.metrics_stream_command import build_metrics_stream_command

    command = build_metrics_stream_command(sample_interval_seconds=0.25, disk_interval_seconds=5.0)

    assert (
        "nvidia-smi --query-gpu=index,name,utilization.gpu,memory.used,memory.total,temperature.gpu "
        "--format=csv,noheader,nounits"
    ) in command


def test_build_metrics_stream_command_emits_one_json_object_per_iteration():
    from server_monitor.dashboard.metrics_stream_command import build_metrics_stream_command

    command = build_metrics_stream_command(sample_interval_seconds=0.25, disk_interval_seconds=5.0)

    assert "printf '%s\\n' \"$JSON_LINE\"" in command


def test_build_metrics_stream_command_emits_millisecond_precision_server_time():
    from server_monitor.dashboard.metrics_stream_command import build_metrics_stream_command

    command = build_metrics_stream_command(sample_interval_seconds=0.25, disk_interval_seconds=5.0)

    assert 'date -u +"%Y-%m-%dT%H:%M:%S.%3N+00:00"' in command
