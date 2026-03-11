from server_monitor.dashboard.command_policy import (
    CommandKind,
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
