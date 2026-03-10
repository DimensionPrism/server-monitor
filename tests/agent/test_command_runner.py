import pytest


@pytest.mark.asyncio
async def test_command_runner_returns_stdout():
    from server_monitor.agent.command_runner import CommandRunner

    runner = CommandRunner(timeout_seconds=1)
    result = await runner.run(["python", "-c", "print('ok')"])

    assert result.exit_code == 0
    assert result.stdout.strip() == "ok"


@pytest.mark.asyncio
async def test_command_runner_handles_non_zero_exit():
    from server_monitor.agent.command_runner import CommandRunner

    runner = CommandRunner(timeout_seconds=1)
    result = await runner.run(["python", "-c", "import sys; sys.exit(3)"])

    assert result.exit_code == 3
    assert result.error is None


@pytest.mark.asyncio
async def test_command_runner_timeout_sets_error():
    from server_monitor.agent.command_runner import CommandRunner

    runner = CommandRunner(timeout_seconds=0.01)
    result = await runner.run(["python", "-c", "import time; time.sleep(0.2)"])

    assert result.exit_code == -1
    assert result.error == "timeout"
