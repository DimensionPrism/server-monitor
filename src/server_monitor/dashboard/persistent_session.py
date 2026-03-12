"""Persistent per-alias SSH transport for batched dashboard polling."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
import re
import time
import uuid

from server_monitor.dashboard.command_runner import CommandResult


_DONE_RE = re.compile(r"^__SM_DONE__ ([a-f0-9]+) (-?\d+)\r?\n?$")


class PersistentSessionProtocolError(RuntimeError):
    """Raised when a persistent shell session violates the framing contract."""


class PersistentBatchTransport:
    """Reuse one long-lived shell per alias for batched dashboard commands."""

    def __init__(
        self,
        *,
        process_factory: Callable[[str], Awaitable[object]] | None = None,
    ) -> None:
        self._process_factory = process_factory or _create_ssh_process
        self._sessions: dict[str, _PersistentBatchSession] = {}

    async def run(self, alias: str, remote_command: str, *, timeout_seconds: float) -> CommandResult:
        session = self._sessions.get(alias)
        if session is None:
            session = _PersistentBatchSession(await self._process_factory(alias))
            self._sessions[alias] = session

        try:
            return await session.run(remote_command, timeout_seconds=timeout_seconds)
        except Exception:
            await self._discard_session(alias)
            raise

    async def close(self) -> None:
        aliases = list(self._sessions.keys())
        for alias in aliases:
            await self._discard_session(alias)

    async def _discard_session(self, alias: str) -> None:
        session = self._sessions.pop(alias, None)
        if session is None:
            return
        await session.close()


class _PersistentBatchSession:
    def __init__(self, process) -> None:
        self._process = process

    async def run(self, remote_command: str, *, timeout_seconds: float) -> CommandResult:
        request_id = uuid.uuid4().hex
        wrapped_command = (
            f"{remote_command}\n"
            "__sm_exit=$?\n"
            f"printf '\\n__SM_DONE__ {request_id} %s\\n' \"$__sm_exit\"\n"
        )
        started_at = time.monotonic()
        self._process.stdin.write(wrapped_command.encode())
        await self._process.stdin.drain()
        return await asyncio.wait_for(
            self._read_until_done(request_id=request_id, started_at=started_at),
            timeout=timeout_seconds,
        )

    async def close(self) -> None:
        self._process.kill()
        await self._process.wait()

    async def _read_until_done(self, *, request_id: str, started_at: float) -> CommandResult:
        payload_lines: list[str] = []
        while True:
            line = await self._process.stdout.readline()
            if line == b"":
                raise PersistentSessionProtocolError("session closed before completion marker")

            decoded_line = line.decode(errors="replace")
            if decoded_line.startswith("__SM_DONE__ "):
                match = _DONE_RE.match(decoded_line)
                if match is None:
                    raise PersistentSessionProtocolError("malformed completion marker")
                completion_id = match.group(1)
                if completion_id != request_id:
                    raise PersistentSessionProtocolError("unexpected completion marker")
                duration_ms = int((time.monotonic() - started_at) * 1000)
                return CommandResult(
                    stdout="".join(payload_lines),
                    stderr="",
                    exit_code=int(match.group(2)),
                    duration_ms=duration_ms,
                )

            payload_lines.append(decoded_line)


async def _create_ssh_process(alias: str):
    return await asyncio.create_subprocess_exec(
        "ssh",
        alias,
        "sh",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
