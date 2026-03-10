"""Async shell command execution for agent collectors."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass


@dataclass(slots=True)
class CommandResult:
    """Result from one shell command execution."""

    stdout: str
    stderr: str
    exit_code: int
    duration_ms: int
    error: str | None = None


class CommandRunner:
    """Run shell commands with timeout control."""

    def __init__(self, timeout_seconds: float = 5.0) -> None:
        self.timeout_seconds = timeout_seconds

    async def run(self, argv: list[str]) -> CommandResult:
        start = time.monotonic()
        process = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(),
                timeout=self.timeout_seconds,
            )
            duration_ms = int((time.monotonic() - start) * 1000)
            return CommandResult(
                stdout=stdout_bytes.decode(errors="replace"),
                stderr=stderr_bytes.decode(errors="replace"),
                exit_code=process.returncode if process.returncode is not None else -1,
                duration_ms=duration_ms,
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.communicate()
            duration_ms = int((time.monotonic() - start) * 1000)
            return CommandResult(
                stdout="",
                stderr="",
                exit_code=-1,
                duration_ms=duration_ms,
                error="timeout",
            )

