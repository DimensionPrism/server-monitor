"""Command execution with retry policy extracted from runtime.py."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from types import SimpleNamespace
import time

from server_monitor.dashboard.health.command_policy import (
    CommandHealthRecord,
    CommandKind,
    CommandPolicy,
    classify_failure,
)
from server_monitor.dashboard.runtime.runtime_helpers import (
    _is_ssh_unreachable,
    _should_retry,
)


@dataclass(slots=True)
class _PolicyExecutionOutcome:
    result: object
    parsed: object | None
    failure_class: str
    attempt_count: int
    message: str
    had_host_unreachable: bool = False
    host_unreachable_message: str = ""


@dataclass(slots=True)
class _SkippedCommandResult:
    stdout: str = ""
    stderr: str = ""
    exit_code: int = -1
    error: str | None = "cooldown_skip"


class CommandExecutor:
    def __init__(self, runtime) -> None:
        self._runtime = runtime

    async def execute_with_policy(
        self,
        *,
        server_id: str,
        ssh_alias: str,
        command_kind: CommandKind,
        target_label: str,
        remote_command: str,
        policy: CommandPolicy,
        parse_output=None,
        cache_used: bool,
    ) -> _PolicyExecutionOutcome:
        attempt_durations_ms: list[int] = []
        had_host_unreachable = False
        host_unreachable_message = ""
        tracker = self._runtime._health.failure_tracker_for(
            server_id=server_id,
            command_kind=command_kind,
            target_label=target_label,
            policy=policy,
        )
        if tracker.in_cooldown(now=time.monotonic()):
            skipped_result = _SkippedCommandResult()
            self._runtime._health.append_command_health(
                CommandHealthRecord(
                    recorded_at=datetime.now(UTC).isoformat(),
                    server_id=server_id,
                    command_kind=command_kind,
                    target_label=target_label,
                    ok=False,
                    failure_class="cooldown_skip",
                    attempt_count=0,
                    duration_ms=0,
                    attempt_durations_ms=[],
                    exit_code=skipped_result.exit_code,
                    cooldown_applied=True,
                    cache_used=cache_used,
                    message="cooldown active",
                )
            )
            return _PolicyExecutionOutcome(
                result=skipped_result,
                parsed=None,
                failure_class="cooldown_skip",
                attempt_count=0,
                message="cooldown active",
                had_host_unreachable=False,
                host_unreachable_message="",
            )

        for attempt in range(1, policy.max_attempts + 1):
            started_at = time.monotonic()
            result = await self._runtime._run_executor(
                ssh_alias,
                remote_command,
                timeout_seconds=policy.timeout_seconds,
            )
            measured_duration_ms = int((time.monotonic() - started_at) * 1000)
            duration_ms = int(getattr(result, "duration_ms", measured_duration_ms))
            attempt_durations_ms.append(duration_ms)

            if result.exit_code == 0 and not result.error:
                if parse_output is not None:
                    try:
                        parsed = parse_output(result.stdout)
                    except Exception as exc:
                        message = str(exc)
                        cooldown_applied = tracker.record_failure(now=time.monotonic())
                        self._runtime._health.append_command_health(
                            CommandHealthRecord(
                                recorded_at=datetime.now(UTC).isoformat(),
                                server_id=server_id,
                                command_kind=command_kind,
                                target_label=target_label,
                                ok=False,
                                failure_class="parse_error",
                                attempt_count=attempt,
                                duration_ms=sum(attempt_durations_ms),
                                attempt_durations_ms=list(attempt_durations_ms),
                                exit_code=int(getattr(result, "exit_code", -1)),
                                cooldown_applied=cooldown_applied,
                                cache_used=cache_used,
                                message=message,
                            )
                        )
                        return _PolicyExecutionOutcome(
                            result=result,
                            parsed=None,
                            failure_class="parse_error",
                            attempt_count=attempt,
                            message=message,
                            had_host_unreachable=had_host_unreachable,
                            host_unreachable_message=host_unreachable_message,
                        )
                else:
                    parsed = None

                tracker.record_success()
                self._runtime._health.append_command_health(
                    CommandHealthRecord(
                        recorded_at=datetime.now(UTC).isoformat(),
                        server_id=server_id,
                        command_kind=command_kind,
                        target_label=target_label,
                        ok=True,
                        failure_class="ok",
                        attempt_count=attempt,
                        duration_ms=sum(attempt_durations_ms),
                        attempt_durations_ms=list(attempt_durations_ms),
                        exit_code=int(getattr(result, "exit_code", 0)),
                        cooldown_applied=False,
                        cache_used=False,
                        message="",
                    )
                )
                return _PolicyExecutionOutcome(
                    result=result,
                    parsed=parsed,
                    failure_class="ok",
                    attempt_count=attempt,
                    message="",
                    had_host_unreachable=had_host_unreachable,
                    host_unreachable_message=host_unreachable_message,
                )

            failure_class = classify_failure(
                error=getattr(result, "error", None),
                stderr=str(getattr(result, "stderr", "")),
            )
            message = str(
                getattr(result, "error", "")
                or getattr(result, "stderr", "")
                or command_kind.value
            )
            if _is_ssh_unreachable(result):
                had_host_unreachable = True
                if not host_unreachable_message:
                    host_unreachable_message = message
            if attempt < policy.max_attempts and _should_retry(
                policy=policy, failure_class=failure_class
            ):
                await asyncio.sleep(policy.base_backoff_seconds * attempt)
                continue

            cooldown_applied = tracker.record_failure(now=time.monotonic())
            self._runtime._health.append_command_health(
                CommandHealthRecord(
                    recorded_at=datetime.now(UTC).isoformat(),
                    server_id=server_id,
                    command_kind=command_kind,
                    target_label=target_label,
                    ok=False,
                    failure_class=failure_class,
                    attempt_count=attempt,
                    duration_ms=sum(attempt_durations_ms),
                    attempt_durations_ms=list(attempt_durations_ms),
                    exit_code=int(getattr(result, "exit_code", -1)),
                    cooldown_applied=cooldown_applied,
                    cache_used=cache_used,
                    message=message,
                )
            )
            return _PolicyExecutionOutcome(
                result=result,
                parsed=None,
                failure_class=failure_class,
                attempt_count=attempt,
                message=message,
                had_host_unreachable=had_host_unreachable,
                host_unreachable_message=host_unreachable_message,
            )

        raise RuntimeError("policy execution exited without result")

    def record_batch_failure(
        self,
        *,
        server_id: str,
        command_kind: CommandKind,
        target_label: str,
        result,
        policy: CommandPolicy,
        cache_used: bool,
    ) -> _PolicyExecutionOutcome:
        failure_class = classify_failure(
            error=getattr(result, "error", None), stderr=getattr(result, "stderr", "")
        )
        message = (
            getattr(result, "error", None)
            or getattr(result, "stderr", "")
            or "batch failed"
        )
        tracker = self._runtime._health.failure_tracker_for(
            server_id=server_id,
            command_kind=command_kind,
            target_label=target_label,
            policy=policy,
        )
        cooldown_applied = tracker.record_failure(now=time.monotonic())
        had_host_unreachable = _is_ssh_unreachable(result)
        host_unreachable_message = message if had_host_unreachable else ""
        duration_ms = int(getattr(result, "duration_ms", 0))
        self._runtime._health.append_command_health(
            CommandHealthRecord(
                recorded_at=datetime.now(UTC).isoformat(),
                server_id=server_id,
                command_kind=command_kind,
                target_label=target_label,
                ok=False,
                failure_class=failure_class,
                attempt_count=1,
                duration_ms=duration_ms,
                attempt_durations_ms=[duration_ms],
                exit_code=int(getattr(result, "exit_code", -1)),
                cooldown_applied=cooldown_applied,
                cache_used=cache_used,
                message=message,
            )
        )
        return _PolicyExecutionOutcome(
            result=result,
            parsed=None,
            failure_class=failure_class,
            attempt_count=1,
            message=message,
            had_host_unreachable=had_host_unreachable,
            host_unreachable_message=host_unreachable_message,
        )

    def record_batch_section_outcome(
        self,
        *,
        server_id: str,
        command_kind: CommandKind,
        target_label: str,
        section_group: dict[str, object] | None,
        policy: CommandPolicy,
        parse_output,
        cache_used: bool,
        fallback_duration_ms: int,
    ) -> _PolicyExecutionOutcome:
        if section_group is None:
            missing_result = SimpleNamespace(
                stdout="",
                stderr="missing batch section",
                exit_code=-1,
                duration_ms=fallback_duration_ms,
                error="parse_error",
            )
            return self.record_batch_failure(
                server_id=server_id,
                command_kind=command_kind,
                target_label=target_label,
                result=missing_result,
                policy=policy,
                cache_used=cache_used,
            )

        stdout_section = section_group.get("stdout")
        stderr_section = section_group.get("stderr")
        result = SimpleNamespace(
            stdout=stdout_section.payload if stdout_section is not None else "",
            stderr=stderr_section.payload if stderr_section is not None else "",
            exit_code=stdout_section.exit_code if stdout_section is not None else -1,
            duration_ms=stdout_section.duration_ms
            if stdout_section is not None
            else fallback_duration_ms,
            error=None,
        )

        tracker = self._runtime._health.failure_tracker_for(
            server_id=server_id,
            command_kind=command_kind,
            target_label=target_label,
            policy=policy,
        )
        if result.exit_code == 0:
            try:
                parsed = parse_output(result.stdout)
            except Exception as exc:
                parse_result = SimpleNamespace(
                    stdout=result.stdout,
                    stderr=str(exc),
                    exit_code=result.exit_code,
                    duration_ms=result.duration_ms,
                    error="parse_error",
                )
                return self.record_batch_failure(
                    server_id=server_id,
                    command_kind=command_kind,
                    target_label=target_label,
                    result=parse_result,
                    policy=policy,
                    cache_used=cache_used,
                )

            tracker.record_success()
            self._runtime._health.append_command_health(
                CommandHealthRecord(
                    recorded_at=datetime.now(UTC).isoformat(),
                    server_id=server_id,
                    command_kind=command_kind,
                    target_label=target_label,
                    ok=True,
                    failure_class="ok",
                    attempt_count=1,
                    duration_ms=result.duration_ms,
                    attempt_durations_ms=[result.duration_ms],
                    exit_code=result.exit_code,
                    cooldown_applied=False,
                    cache_used=cache_used,
                    message="ok",
                )
            )
            return _PolicyExecutionOutcome(
                result=result,
                parsed=parsed,
                failure_class="ok",
                attempt_count=1,
                message="ok",
            )

        return self.record_batch_failure(
            server_id=server_id,
            command_kind=command_kind,
            target_label=target_label,
            result=result,
            policy=policy,
            cache_used=cache_used,
        )
