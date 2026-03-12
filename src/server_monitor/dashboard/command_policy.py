"""Policy primitives for command execution resilience."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import re


class CommandKind(StrEnum):
    """Stable command names used for policy lookup and journaling."""

    SYSTEM = "system"
    GPU = "gpu"
    GIT_STATUS = "git_status"
    CLASH_SECRET = "clash_secret"
    CLASH_PROBE = "clash_probe"
    GIT_OPERATION = "git_operation"


@dataclass(frozen=True, slots=True)
class CommandPolicy:
    """Retry and cooldown policy for one command kind."""

    timeout_seconds: float
    max_attempts: int
    base_backoff_seconds: float
    retry_on_timeout: bool = True
    retry_on_ssh_error: bool = True
    retry_on_nonzero_exit: bool = False
    cooldown_after_failures: int = 3
    cooldown_seconds: float = 15.0


@dataclass(slots=True)
class FailureTracker:
    """Track consecutive failures and short cooldown windows."""

    cooldown_after_failures: int
    cooldown_seconds: float
    consecutive_failures: int = 0
    cooldown_until: float = 0.0

    def record_failure(self, *, now: float) -> bool:
        """Record one failure and return whether cooldown started."""

        self.consecutive_failures += 1
        if self.consecutive_failures < self.cooldown_after_failures:
            return False
        self.cooldown_until = now + self.cooldown_seconds
        return True

    def record_success(self) -> None:
        """Reset failure streak after a successful execution."""

        self.consecutive_failures = 0
        self.cooldown_until = 0.0

    def in_cooldown(self, *, now: float) -> bool:
        """Return whether the tracker is currently suppressing retries."""

        return now < self.cooldown_until


@dataclass(slots=True)
class CommandHealthRecord:
    """Redaction-safe summary of one command execution."""

    recorded_at: str
    server_id: str
    command_kind: CommandKind
    target_label: str
    ok: bool
    failure_class: str
    attempt_count: int
    duration_ms: int
    attempt_durations_ms: list[int]
    exit_code: int
    cooldown_applied: bool
    cache_used: bool
    message: str

    def __post_init__(self) -> None:
        self.message = redact_sensitive_text(self.message)


def default_command_policies() -> dict[CommandKind, CommandPolicy]:
    """Return the default policy table for dashboard commands."""

    return {
        CommandKind.SYSTEM: CommandPolicy(timeout_seconds=3.0, max_attempts=2, base_backoff_seconds=0.1),
        CommandKind.GPU: CommandPolicy(timeout_seconds=3.0, max_attempts=2, base_backoff_seconds=0.1),
        CommandKind.GIT_STATUS: CommandPolicy(
            timeout_seconds=10.0,
            max_attempts=1,
            base_backoff_seconds=0.1,
            retry_on_nonzero_exit=True,
        ),
        CommandKind.CLASH_SECRET: CommandPolicy(
            timeout_seconds=3.0,
            max_attempts=2,
            base_backoff_seconds=0.1,
            retry_on_nonzero_exit=True,
        ),
        CommandKind.CLASH_PROBE: CommandPolicy(
            timeout_seconds=3.0,
            max_attempts=2,
            base_backoff_seconds=0.1,
            retry_on_nonzero_exit=True,
        ),
        CommandKind.GIT_OPERATION: CommandPolicy(
            timeout_seconds=20.0,
            max_attempts=1,
            base_backoff_seconds=0.0,
            retry_on_nonzero_exit=False,
        ),
    }


def classify_failure(*, error: str | None, stderr: str) -> str:
    """Map raw execution details onto stable failure classes."""

    if error == "parse_error":
        return "parse_error"
    if error == "timeout":
        return "timeout"
    lower_stderr = (stderr or "").lower()
    if any(
        token in lower_stderr
        for token in [
            "timed out",
            "timeout",
            "could not resolve hostname",
            "connection refused",
            "network is unreachable",
            "no route to host",
        ]
    ):
        return "ssh_unreachable"
    if error:
        return "unexpected"
    if lower_stderr:
        return "nonzero_exit"
    return "ok"


def redact_sensitive_text(text: str) -> str:
    """Remove obvious secret-bearing tokens from diagnostic text."""

    redacted = re.sub(r"(authorization:\s*bearer\s+)\S+", r"\1[REDACTED]", text, flags=re.IGNORECASE)
    redacted = re.sub(r"(secret\s*[:=]\s*)\S+", r"\1[REDACTED]", redacted, flags=re.IGNORECASE)
    redacted = re.sub(r"(当前密钥\s*[:：]\s*)\S+", r"\1[REDACTED]", redacted, flags=re.IGNORECASE)
    return redacted
