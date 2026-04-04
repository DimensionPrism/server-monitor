from server_monitor.dashboard.health.command_policy import (
    CommandHealthRecord,
    CommandKind,
    FailureTracker,
    classify_failure,
    default_command_policies,
    redact_sensitive_text,
)


def test_timeout_is_retryable_for_system_policy():
    policies = default_command_policies()
    policy = policies[CommandKind.SYSTEM]

    assert policy.retry_on_timeout is True
    assert policy.max_attempts == 2


def test_parse_error_is_not_retryable():
    assert classify_failure(error="parse_error", stderr="") == "parse_error"


def test_redact_sensitive_text_masks_bearer_secret():
    text = "Authorization: Bearer mysecret"

    assert "mysecret" not in redact_sensitive_text(text)


def test_failure_streak_triggers_cooldown_after_threshold():
    tracker = FailureTracker(cooldown_after_failures=2, cooldown_seconds=10.0)

    assert tracker.record_failure(now=10.0) is False
    assert tracker.record_failure(now=12.0) is True
    assert tracker.in_cooldown(now=20.0) is True
    assert tracker.in_cooldown(now=23.0) is False


def test_command_health_record_omits_raw_command_text():
    record = CommandHealthRecord(
        recorded_at="2026-03-11T10:00:00+00:00",
        server_id="srv-a",
        command_kind=CommandKind.CLASH_PROBE,
        target_label="server",
        ok=False,
        failure_class="nonzero_exit",
        attempt_count=1,
        duration_ms=75,
        attempt_durations_ms=[75],
        exit_code=1,
        cooldown_applied=False,
        cache_used=False,
        message="Authorization: Bearer mysecret",
    )

    assert "mysecret" not in record.message


def test_redact_sensitive_text_masks_chinese_secret_label():
    text = "当前密钥：mysecret"

    assert "mysecret" not in redact_sensitive_text(text)
