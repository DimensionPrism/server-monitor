import pytest

from server_monitor.dashboard.batch_protocol import (
    BatchProtocolError,
    BatchSection,
    build_metrics_batch_command,
    build_status_batch_command,
    parse_batch_output,
)


def test_parse_batch_output_returns_sections_in_order():
    token = "SMTOKEN"
    output = (
        "SMTOKEN BEGIN kind=system target=server exit=0 duration_ms=123 stream=stdout\n"
        "CPU: 11.0\n"
        "SMTOKEN END\n"
        "SMTOKEN BEGIN kind=gpu target=server exit=0 duration_ms=98 stream=stdout\n"
        "0, NVIDIA A100, 70, 1024, 40960, 50\n"
        "SMTOKEN END\n"
    )

    sections = parse_batch_output(output, token=token)

    assert sections == [
        BatchSection(
            kind="system",
            target="server",
            exit_code=0,
            duration_ms=123,
            stream="stdout",
            payload="CPU: 11.0\n",
        ),
        BatchSection(
            kind="gpu",
            target="server",
            exit_code=0,
            duration_ms=98,
            stream="stdout",
            payload="0, NVIDIA A100, 70, 1024, 40960, 50\n",
        ),
    ]


def test_parse_batch_output_rejects_missing_end_marker():
    token = "SMTOKEN"
    output = (
        "SMTOKEN BEGIN kind=system target=server exit=0 duration_ms=123 stream=stdout\n"
        "CPU: 11.0\n"
    )

    with pytest.raises(BatchProtocolError, match="unterminated"):
        parse_batch_output(output, token=token)


def test_build_metrics_batch_command_includes_both_metric_commands_and_framing():
    command = build_metrics_batch_command(
        token="SMTOKEN",
        system_command="echo SYSTEM",
        gpu_command="echo GPU",
    )

    assert "echo SYSTEM" in command
    assert "echo GPU" in command
    assert "SMTOKEN BEGIN kind=system target=server" in command
    assert "SMTOKEN BEGIN kind=gpu target=server" in command


def test_build_status_batch_command_includes_repo_and_clash_commands():
    command = build_status_batch_command(
        token="SMTOKEN",
        git_commands=[
            ("/work/repo-a", "git -C '/work/repo-a' status --porcelain --branch"),
            ("/work/repo-b", "git -C '/work/repo-b' status --porcelain --branch"),
        ],
        clash_secret_command="clashsecret",
        clash_probe_command="curl http://127.0.0.1:9090/version",
    )

    assert "git -C '/work/repo-a' status --porcelain --branch" in command
    assert "git -C '/work/repo-b' status --porcelain --branch" in command
    assert "clashsecret" in command
    assert "curl http://127.0.0.1:9090/version" in command
    assert "SMTOKEN BEGIN kind=git_status target=/work/repo-a" in command
    assert "SMTOKEN BEGIN kind=clash_secret target=server" in command
    assert "SMTOKEN BEGIN kind=clash_probe target=server" in command
