def test_build_metrics_stream_command_contains_sampling_loop():
    from server_monitor.dashboard.metrics.command import build_metrics_stream_command

    command = build_metrics_stream_command(
        sample_interval_seconds=0.25, disk_interval_seconds=5.0
    )

    assert "while :" in command
    assert "sleep 0.25" in command


def test_build_metrics_stream_command_reads_proc_net_dev_for_network_deltas():
    from server_monitor.dashboard.metrics.command import build_metrics_stream_command

    command = build_metrics_stream_command(
        sample_interval_seconds=0.25, disk_interval_seconds=5.0
    )

    assert "/proc/net/dev" in command
    assert "PREV_RX_BYTES" in command
    assert "PREV_TX_BYTES" in command


def test_build_metrics_stream_command_refreshes_disk_less_often_than_every_sample():
    from server_monitor.dashboard.metrics.command import build_metrics_stream_command

    command = build_metrics_stream_command(
        sample_interval_seconds=0.25, disk_interval_seconds=5.0
    )

    assert "DISK_REFRESH_TICKS=20" in command
    assert "DISK_TICK=0" in command


def test_build_metrics_stream_command_queries_gpu_every_sample():
    from server_monitor.dashboard.metrics.command import build_metrics_stream_command

    command = build_metrics_stream_command(
        sample_interval_seconds=0.25, disk_interval_seconds=5.0
    )

    assert (
        "nvidia-smi --query-gpu=index,name,utilization.gpu,memory.used,memory.total,temperature.gpu "
        "--format=csv,noheader,nounits"
    ) in command


def test_build_metrics_stream_command_sanitizes_non_numeric_gpu_fields():
    from server_monitor.dashboard.metrics.command import build_metrics_stream_command

    command = build_metrics_stream_command(
        sample_interval_seconds=0.25, disk_interval_seconds=5.0
    )

    assert "if (util !~ /^-?[0-9]+(\\.[0-9]+)?$/) util = 0" in command
    assert "if (mem_used !~ /^-?[0-9]+(\\.[0-9]+)?$/) mem_used = 0" in command
    assert "if (mem_total !~ /^-?[0-9]+(\\.[0-9]+)?$/) mem_total = 0" in command
    assert "if (temp !~ /^-?[0-9]+(\\.[0-9]+)?$/) temp = 0" in command


def test_build_metrics_stream_command_includes_tegrastats_cache_refresh():
    from server_monitor.dashboard.metrics.command import build_metrics_stream_command

    command = build_metrics_stream_command(
        sample_interval_seconds=0.25, disk_interval_seconds=5.0
    )

    assert "TEGRASTATS_REFRESH_TICKS=1" in command
    assert "if command -v tegrastats >/dev/null 2>&1; then" in command
    assert "refresh_tegrastats_cache" in command


def test_build_metrics_stream_command_uses_tegrastats_when_nvidia_smi_returns_na():
    from server_monitor.dashboard.metrics.command import build_metrics_stream_command

    command = build_metrics_stream_command(
        sample_interval_seconds=0.25, disk_interval_seconds=5.0
    )

    assert "if printf '%s\\n' \"$GPU_LINES\" | grep -q '\\[N/A\\]'; then" in command
    assert "build_tegrastats_gpu_json" in command
    assert '"name":"Jetson iGPU"' in command


def test_build_metrics_stream_command_runs_tegrastats_as_background_collector():
    from server_monitor.dashboard.metrics.command import build_metrics_stream_command

    command = build_metrics_stream_command(
        sample_interval_seconds=0.25, disk_interval_seconds=5.0
    )

    assert "TEGRASTATS_LOG=$(mktemp)" in command
    assert (
        'tegrastats --interval "$TEGRASTATS_SAMPLE_MS" >"$TEGRASTATS_LOG" 2>/dev/null &'
        in command
    )
    assert 'tail -n 1 "$TEGRASTATS_LOG"' in command
    assert "timeout 2 tegrastats --interval 1000" not in command


def test_build_metrics_stream_command_emits_one_json_object_per_iteration():
    from server_monitor.dashboard.metrics.command import build_metrics_stream_command

    command = build_metrics_stream_command(
        sample_interval_seconds=0.25, disk_interval_seconds=5.0
    )

    assert "printf '%s\\n' \"$JSON_LINE\"" in command


def test_build_metrics_stream_command_emits_millisecond_precision_server_time():
    from server_monitor.dashboard.metrics.command import build_metrics_stream_command

    command = build_metrics_stream_command(
        sample_interval_seconds=0.25, disk_interval_seconds=5.0
    )

    assert 'date -u +"%Y-%m-%dT%H:%M:%S.%3N+00:00"' in command
