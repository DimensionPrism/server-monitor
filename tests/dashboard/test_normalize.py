from datetime import UTC, datetime, timedelta


def test_normalize_marks_stale_when_timestamp_exceeds_threshold():
    from server_monitor.dashboard.normalize import normalize_server_payload

    now = datetime(2026, 3, 10, tzinfo=UTC)
    payload = {
        "timestamp": (now - timedelta(seconds=20)).isoformat(),
        "snapshot": {"cpu_percent": 10.0},
        "repos": [],
        "clash": {"running": True},
    }

    normalized = normalize_server_payload(
        server_id="server-a",
        payload=payload,
        now=now,
        stale_after_seconds=10,
    )

    assert normalized["server_id"] == "server-a"
    assert normalized["stale"] is True


def test_normalize_marks_fresh_with_recent_timestamp():
    from server_monitor.dashboard.normalize import normalize_server_payload

    now = datetime(2026, 3, 10, tzinfo=UTC)
    payload = {
        "timestamp": (now - timedelta(seconds=2)).isoformat(),
        "snapshot": {"cpu_percent": 10.0},
        "repos": [],
        "clash": {"running": True},
    }

    normalized = normalize_server_payload(
        server_id="server-a",
        payload=payload,
        now=now,
        stale_after_seconds=10,
    )

    assert normalized["stale"] is False
