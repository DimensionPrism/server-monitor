"""Pure helper functions extracted from runtime.py."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from server_monitor.dashboard.health.command_policy import CommandPolicy

if TYPE_CHECKING:
    from server_monitor.dashboard.settings import ServerSettings

DEFAULT_CLASH = {
    "running": False,
    "api_reachable": False,
    "ui_reachable": False,
    "message": "not-collected",
    "ip_location": "",
    "controller_port": "",
}
GIT_OPERATION_TIMEOUT_SECONDS = 20.0
STATUS_COMMAND_TIMEOUT_SECONDS = 3.0
STATUS_POLL_INLINE_BUDGET_SECONDS = 0.05


def _needs_status_poll(
    *, last: datetime | None, now: datetime, interval_seconds: float
) -> bool:
    if last is None:
        return True
    return (now - last).total_seconds() >= interval_seconds


def _metrics_sleep_seconds(*, interval_seconds: float, elapsed_seconds: float) -> float:
    target_interval_seconds = max(0.5, interval_seconds)
    return max(0.05, target_interval_seconds - elapsed_seconds)


def _find_server(servers: list[ServerSettings], server_id: str) -> ServerSettings:
    for server in servers:
        if server.server_id == server_id:
            return server
    raise KeyError(f"unknown server '{server_id}'")


def _is_ssh_unreachable(result) -> bool:
    blob = f"{result.error or ''} {result.stderr or ''}".lower()
    return any(
        token in blob
        for token in [
            "timeout",
            "timed out",
            "could not resolve hostname",
            "connection refused",
            "network is unreachable",
            "no route to host",
        ]
    )


def _group_batch_sections(sections) -> dict[tuple[str, str], dict[str, object]]:
    grouped: dict[tuple[str, str], dict[str, object]] = {}
    for section in sections:
        grouped.setdefault((section.kind, section.target), {})[section.stream] = section
    return grouped


def _empty_repo_status(path: str) -> dict[str, str | int | bool | None]:
    return {
        "path": path,
        "branch": "unknown",
        "dirty": False,
        "ahead": 0,
        "behind": 0,
        "staged": 0,
        "unstaged": 0,
        "untracked": 0,
        "last_commit_age_seconds": 0,
        "last_updated_at": None,
    }


def _empty_system_snapshot() -> dict[str, float]:
    return {
        "cpu_percent": 0.0,
        "memory_percent": 0.0,
        "disk_percent": 0.0,
        "network_rx_kbps": 0.0,
        "network_tx_kbps": 0.0,
    }


def _should_retry(*, policy: CommandPolicy, failure_class: str) -> bool:
    if failure_class == "timeout":
        return policy.retry_on_timeout
    if failure_class == "ssh_unreachable":
        return policy.retry_on_ssh_error
    if failure_class == "nonzero_exit":
        return policy.retry_on_nonzero_exit
    return False


def _build_freshness_entry(
    *,
    now: datetime,
    last_updated_at: str | None,
    last_poll_ok: bool | None,
    threshold_seconds: float,
    keep_live_while_inflight: bool = False,
) -> dict[str, str | int | float | None]:
    age_seconds = _age_seconds_from_iso(now=now, timestamp_iso=last_updated_at)
    normalized_threshold = float(max(1.0, threshold_seconds))

    if last_poll_ok is False:
        state = "cached"
        reason = "poll_error"
    elif age_seconds is None:
        state = "cached"
        reason = "no_data"
    elif age_seconds > normalized_threshold:
        if keep_live_while_inflight:
            state = "live"
            reason = "poll_inflight"
        else:
            state = "cached"
            reason = "age_expired"
    else:
        state = "live"
        reason = "ok"

    return {
        "state": state,
        "reason": reason,
        "last_updated_at": last_updated_at,
        "age_seconds": age_seconds if age_seconds is not None else 0,
        "threshold_seconds": normalized_threshold,
    }


def _age_seconds_from_iso(*, now: datetime, timestamp_iso: str | None) -> int | None:
    if not timestamp_iso:
        return None
    try:
        parsed = datetime.fromisoformat(timestamp_iso)
    except ValueError:
        return None
    return max(0, int((now - parsed).total_seconds()))


def _metrics_stream_transport_latency_ms(
    *,
    sample_server_time: str | None,
    received_at: datetime,
    sample_interval_ms: int | None = None,
) -> int | None:
    if not sample_server_time:
        return None
    try:
        parsed = datetime.fromisoformat(sample_server_time)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    latency_ms = int((received_at - parsed).total_seconds() * 1000)
    if latency_ms < 0:
        return None
    max_latency_ms = _metrics_stream_latency_upper_bound_ms(sample_interval_ms)
    if latency_ms > max_latency_ms:
        return None
    return latency_ms


def _metrics_stream_latency_upper_bound_ms(sample_interval_ms: int | None) -> int:
    floor_ms = 5000
    multiplier = 20
    if sample_interval_ms is None:
        return floor_ms
    try:
        interval_ms = int(sample_interval_ms)
    except (TypeError, ValueError):
        return floor_ms
    if interval_ms <= 0:
        return floor_ms
    return max(floor_ms, interval_ms * multiplier)
