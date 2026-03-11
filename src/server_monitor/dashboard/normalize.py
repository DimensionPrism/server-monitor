"""Normalization utilities for dashboard updates."""

from __future__ import annotations

from datetime import datetime


def normalize_server_payload(
    *,
    server_id: str,
    payload: dict,
    now: datetime,
    stale_after_seconds: float,
) -> dict:
    """Normalize update payload and derive stale status."""

    timestamp_text = payload.get("timestamp")
    source_ts = datetime.fromisoformat(timestamp_text) if timestamp_text else now
    stale = (now - source_ts).total_seconds() > stale_after_seconds

    return {
        "server_id": server_id,
        "timestamp": source_ts.isoformat(),
        "snapshot": payload.get("snapshot", {}),
        "repos": payload.get("repos", []),
        "clash": payload.get("clash", {}),
        "command_health": payload.get("command_health", {}),
        "freshness": payload.get("freshness", {}),
        "enabled_panels": payload.get("enabled_panels", ["system", "gpu", "git", "clash"]),
        "stale": stale,
    }
