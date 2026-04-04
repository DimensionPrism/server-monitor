"""Tests for runtime_helpers module."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest


def test_metrics_sleep_seconds_compensates_poll_time():
    from server_monitor.dashboard.runtime_helpers import _metrics_sleep_seconds

    assert _metrics_sleep_seconds(
        interval_seconds=1.0, elapsed_seconds=0.25
    ) == pytest.approx(0.75)
    assert _metrics_sleep_seconds(
        interval_seconds=1.0, elapsed_seconds=1.6
    ) == pytest.approx(0.05)


def test_batched_clash_secret_command_runs_lookup_in_child_shell():
    from server_monitor.dashboard.runtime_helpers import _batched_clash_secret_command

    command = _batched_clash_secret_command()

    assert "sh -lc" in command


def test_extract_clash_secret_parses_chinese_label_output():
    from server_monitor.dashboard.runtime_helpers import _extract_clash_secret

    text = "😼 当前密钥：mysecret"
    assert _extract_clash_secret(text) == "mysecret"


def test_clash_secret_command_includes_runtime_yaml_fallback():
    from server_monitor.dashboard.runtime_helpers import _clash_secret_command

    cmd = _clash_secret_command()
    assert "clashsecret" in cmd
    assert "runtime.yaml" in cmd
    assert "当前密钥" in cmd


def test_clash_command_includes_bearer_header_for_api_and_ui():
    from server_monitor.dashboard.runtime_helpers import _clash_command

    cmd = _clash_command(
        api_probe_url="http://127.0.0.1:9090/version",
        ui_probe_url="http://127.0.0.1:9090/ui",
        secret="mysecret",
    )
    assert "Authorization: Bearer mysecret" in cmd
    assert cmd.count('-H "$AUTH_HEADER"') >= 2
    assert "127.0.0.1:9090/version" in cmd
    assert "127.0.0.1:9090/ui" in cmd
    assert "-lt 400" in cmd
    assert "ip_location=" in cmd
    assert "controller_port=" in cmd


def test_clash_command_routes_ip_lookup_via_detected_proxy_port():
    from server_monitor.dashboard.runtime_helpers import _clash_command

    cmd = _clash_command(
        api_probe_url="http://127.0.0.1:9090/version",
        ui_probe_url="http://127.0.0.1:9090/ui",
        secret="mysecret",
    )

    assert "mixed-port:" in cmd
    assert "PROXY_URL=" in cmd
    assert '--proxy "$PROXY_URL"' in cmd


def test_clash_command_parses_ip_lookup_fields_in_provider_order():
    from server_monitor.dashboard.runtime_helpers import _clash_command

    cmd = _clash_command(
        api_probe_url="http://127.0.0.1:9090/version",
        ui_probe_url="http://127.0.0.1:9090/ui",
        secret="mysecret",
    )

    assert "IP_COUNTRY=$(printf '%s\\n' \"$IP_INFO\" | sed -n '1p'" in cmd
    assert "IP_REGION=$(printf '%s\\n' \"$IP_INFO\" | sed -n '2p'" in cmd
    assert "IP_CITY=$(printf '%s\\n' \"$IP_INFO\" | sed -n '3p'" in cmd
    assert "IP_ADDR=$(printf '%s\\n' \"$IP_INFO\" | sed -n '4p'" in cmd


def test_metrics_stream_transport_latency_rejects_clock_skew_and_implausible_outliers():
    from server_monitor.dashboard.runtime_helpers import (
        _metrics_stream_transport_latency_ms,
    )

    received_at = datetime(2026, 3, 13, 12, 0, 0, tzinfo=UTC)

    assert (
        _metrics_stream_transport_latency_ms(
            sample_server_time="2026-03-13T12:00:02+00:00",
            received_at=received_at,
            sample_interval_ms=250,
        )
        is None
    )
    assert (
        _metrics_stream_transport_latency_ms(
            sample_server_time="2026-03-13T11:59:50+00:00",
            received_at=received_at,
            sample_interval_ms=250,
        )
        is None
    )
    assert (
        _metrics_stream_transport_latency_ms(
            sample_server_time="2026-03-13T11:59:59.680+00:00",
            received_at=received_at,
            sample_interval_ms=250,
        )
        == 320
    )
