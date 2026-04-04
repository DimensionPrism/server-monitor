"""Command health tracking extracted from runtime.py."""

from __future__ import annotations

from typing import TYPE_CHECKING

from server_monitor.dashboard.command_policy import (
    CommandHealthRecord,
    CommandKind,
    CommandPolicy,
    FailureTracker,
)

if TYPE_CHECKING:
    from server_monitor.dashboard.settings import ServerSettings


def _unknown_command_health_summary() -> dict:
    return {
        "state": "unknown",
        "label": "--",
        "latency_ms": None,
        "detail": "No command history yet",
        "updated_at": None,
    }


def _command_health_summary_from_record(
    record: CommandHealthRecord | None, *, default_detail: str
) -> dict:
    if record is None:
        return _unknown_command_health_summary()

    state = _command_health_state_from_record(record)
    detail = default_detail
    if state == "retrying":
        detail = f"Last poll succeeded after {record.attempt_count} attempts"
    elif state == "cooldown":
        detail = "Command cooling down after repeated failures"
    elif state == "failed":
        detail = record.message or "Last poll failed"

    return {
        "state": state,
        "label": _command_health_label(
            state=state,
            latency_ms=record.duration_ms,
            attempt_count=record.attempt_count,
        ),
        "latency_ms": record.duration_ms,
        "detail": detail,
        "updated_at": record.recorded_at,
    }


def _command_health_state_from_record(record: CommandHealthRecord | None) -> str:
    if record is None:
        return "unknown"
    if record.ok and record.attempt_count > 1:
        return "retrying"
    if record.ok:
        return "healthy"
    if record.failure_class == "cooldown_skip":
        return "cooldown"
    return "failed"


def _command_health_label(
    *, state: str, latency_ms: int | None, attempt_count: int
) -> str:
    if state == "healthy":
        return f"{latency_ms}ms" if latency_ms is not None else "--"
    if state == "retrying":
        return f"retry x{max(attempt_count, 2)}"
    if state == "cooldown":
        return "cooldown"
    if state == "failed":
        return "failed"
    return "--"


def _command_health_severity(state: str) -> int:
    return {
        "unknown": 0,
        "healthy": 1,
        "retrying": 2,
        "cooldown": 3,
        "failed": 4,
    }.get(state, 0)


def _worst_command_health_state(states) -> str:
    state_list = list(states)
    if not state_list:
        return "unknown"
    return max(state_list, key=_command_health_severity)


def _git_command_health_detail(state: str) -> str:
    if state == "healthy":
        return "All repos healthy"
    if state == "retrying":
        return "One or more repos required retries"
    if state == "cooldown":
        return "One or more repos are cooling down"
    if state == "failed":
        return "One or more repos failed"
    return "No repo health history yet"


class CommandHealthTracker:
    def __init__(self, runtime) -> None:
        self._runtime = runtime

    def append_command_health(self, record: CommandHealthRecord) -> None:
        key = (record.server_id, record.command_kind.value, record.target_label)
        history = self._runtime._recent_command_health.setdefault(key, [])
        history.append(record)
        from server_monitor.dashboard.runtime_helpers import (
            COMMAND_HEALTH_HISTORY_LIMIT,
        )

        if len(history) > COMMAND_HEALTH_HISTORY_LIMIT:
            history.pop(0)

    def failure_tracker_for(
        self,
        *,
        server_id: str,
        command_kind: CommandKind,
        target_label: str,
        policy: CommandPolicy,
    ) -> FailureTracker:
        key = (server_id, command_kind.value, target_label)
        tracker = self._runtime._failure_trackers.get(key)
        if tracker is None:
            tracker = FailureTracker(
                cooldown_after_failures=policy.cooldown_after_failures,
                cooldown_seconds=policy.cooldown_seconds,
            )
            self._runtime._failure_trackers[key] = tracker
        return tracker

    def summarize_server_command_health(
        self, *, server: ServerSettings
    ) -> dict[str, dict]:
        summaries: dict[str, dict] = {}
        for panel_name in server.enabled_panels:
            try:
                if panel_name == "system":
                    if self._runtime.metrics_stream_manager is not None:
                        summaries[panel_name] = self.summary_for_metrics_stream(
                            server_id=server.server_id
                        )
                    else:
                        summaries[panel_name] = self.summary_for_single_command(
                            server_id=server.server_id,
                            command_kind=CommandKind.SYSTEM,
                            target_label="server",
                            detail="Last poll succeeded",
                        )
                elif panel_name == "gpu":
                    if self._runtime.metrics_stream_manager is not None:
                        summaries[panel_name] = self.summary_for_metrics_stream(
                            server_id=server.server_id
                        )
                    else:
                        summaries[panel_name] = self.summary_for_single_command(
                            server_id=server.server_id,
                            command_kind=CommandKind.GPU,
                            target_label="server",
                            detail="Last poll succeeded",
                        )
                elif panel_name == "git":
                    summaries[panel_name] = self.summary_for_git(server=server)
                elif panel_name == "clash":
                    summaries[panel_name] = self.summary_for_clash(
                        server_id=server.server_id
                    )
            except Exception:
                summaries[panel_name] = _unknown_command_health_summary()
        return summaries

    def summary_for_metrics_stream(self, *, server_id: str) -> dict:
        stream_status = self._runtime._metrics_stream_status.get(server_id)
        if stream_status is None:
            return _unknown_command_health_summary()

        if stream_status.state == "live":
            latency_ms = stream_status.transport_latency_ms
            return {
                "state": "healthy",
                "label": f"{latency_ms}ms" if latency_ms is not None else "--",
                "latency_ms": latency_ms,
                "detail": "Metrics stream transport latency"
                if latency_ms is not None
                else "Metrics stream active",
                "updated_at": stream_status.last_sample_received_at,
            }
        if stream_status.state == "reconnecting":
            return {
                "state": "retrying",
                "label": "reconnecting",
                "latency_ms": None,
                "detail": "Metrics stream reconnecting",
                "updated_at": stream_status.state_changed_at
                or stream_status.last_sample_received_at,
            }
        if stream_status.state == "connecting":
            return {
                "state": "retrying",
                "label": "connecting",
                "latency_ms": None,
                "detail": "Metrics stream connecting",
                "updated_at": stream_status.state_changed_at,
            }
        if stream_status.state == "stopped":
            return {
                "state": "failed",
                "label": "stopped",
                "latency_ms": None,
                "detail": "Metrics stream stopped",
                "updated_at": stream_status.state_changed_at
                or stream_status.last_sample_received_at,
            }
        return _unknown_command_health_summary()

    def summary_for_single_command(
        self,
        *,
        server_id: str,
        command_kind: CommandKind,
        target_label: str,
        detail: str,
    ) -> dict:
        record = self.latest_command_health_record(
            server_id=server_id,
            command_kind=command_kind,
            target_label=target_label,
        )
        return _command_health_summary_from_record(record, default_detail=detail)

    def summary_for_git(self, *, server: ServerSettings) -> dict:
        records = [
            record
            for repo_path in server.working_dirs
            if (
                record := self.latest_command_health_record(
                    server_id=server.server_id,
                    command_kind=CommandKind.GIT_STATUS,
                    target_label=repo_path,
                )
            )
            is not None
        ]
        if not records:
            return _unknown_command_health_summary()

        state = _worst_command_health_state(
            _command_health_state_from_record(record) for record in records
        )
        if state == "healthy":
            latency_ms = max(record.duration_ms for record in records)
            updated_at = max(record.recorded_at for record in records)
            return {
                "state": state,
                "label": _command_health_label(
                    state=state, latency_ms=latency_ms, attempt_count=1
                ),
                "latency_ms": latency_ms,
                "detail": "All repos healthy",
                "updated_at": updated_at,
            }

        matching_records = [
            record
            for record in records
            if _command_health_state_from_record(record) == state
        ]
        worst_record = max(
            matching_records,
            key=lambda record: (
                _command_health_severity(_command_health_state_from_record(record)),
                record.duration_ms,
            ),
        )
        return {
            "state": state,
            "label": _command_health_label(
                state=state,
                latency_ms=worst_record.duration_ms,
                attempt_count=worst_record.attempt_count,
            ),
            "latency_ms": worst_record.duration_ms,
            "detail": _git_command_health_detail(state),
            "updated_at": worst_record.recorded_at,
        }

    def summary_for_clash(self, *, server_id: str) -> dict:
        secret_record = self.latest_command_health_record(
            server_id=server_id,
            command_kind=CommandKind.CLASH_SECRET,
            target_label="server",
        )
        probe_record = self.latest_command_health_record(
            server_id=server_id,
            command_kind=CommandKind.CLASH_PROBE,
            target_label="server",
        )

        secret_state = _command_health_state_from_record(secret_record)
        probe_state = _command_health_state_from_record(probe_record)

        if secret_state in {"failed", "cooldown", "retrying"}:
            return _command_health_summary_from_record(
                secret_record, default_detail="Secret check failed"
            )
        if probe_record is not None:
            return _command_health_summary_from_record(
                probe_record, default_detail="Last probe succeeded"
            )
        if secret_record is not None:
            return _command_health_summary_from_record(
                secret_record, default_detail="Last secret check succeeded"
            )
        if secret_state == "unknown" and probe_state == "unknown":
            return _unknown_command_health_summary()
        return _unknown_command_health_summary()

    def latest_command_health_record(
        self,
        *,
        server_id: str,
        command_kind: CommandKind,
        target_label: str,
    ) -> CommandHealthRecord | None:
        records = self._runtime._recent_command_health.get(
            (server_id, command_kind.value, target_label), []
        )
        if not records:
            return None
        return records[-1]
