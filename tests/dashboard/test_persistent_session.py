import asyncio
import re

import pytest

from server_monitor.dashboard.persistent_session import PersistentBatchTransport, PersistentSessionProtocolError


class _FakeStreamReader:
    def __init__(self):
        self._queue: asyncio.Queue[bytes] = asyncio.Queue()

    async def readline(self) -> bytes:
        return await self._queue.get()

    def feed_line(self, text: str) -> None:
        self._queue.put_nowait(text.encode())

    def feed_eof(self) -> None:
        self._queue.put_nowait(b"")


class _FakeStreamWriter:
    def __init__(self, process):
        self._process = process

    def write(self, data: bytes) -> None:
        self._process.handle_write(data.decode())

    async def drain(self) -> None:
        return None

    def close(self) -> None:
        self._process.closed = True


class _FakeProcess:
    def __init__(self, scripted_responses):
        self.scripted_responses = list(scripted_responses)
        self.stdout = _FakeStreamReader()
        self.stdin = _FakeStreamWriter(self)
        self.calls = []
        self.closed = False
        self.killed = False
        self.returncode = None

    def handle_write(self, payload: str) -> None:
        self.calls.append(payload)
        request_id_match = re.search(r"__SM_DONE__ ([a-f0-9]+)", payload)
        assert request_id_match is not None
        request_id = request_id_match.group(1)
        response = self.scripted_responses.pop(0)
        response(self, request_id)

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9
        self.stdout.feed_eof()

    async def wait(self) -> int:
        if self.returncode is None:
            self.returncode = 0
        return self.returncode


def _success_response(payload: str):
    def _response(process: _FakeProcess, request_id: str) -> None:
        process.stdout.feed_line(payload)
        process.stdout.feed_line(f"__SM_DONE__ {request_id} 0\n")

    return _response


def _eof_response(process: _FakeProcess, request_id: str) -> None:
    process.returncode = 255
    process.stdout.feed_eof()


def _malformed_response(process: _FakeProcess, request_id: str) -> None:
    process.stdout.feed_line("hello\n")
    process.stdout.feed_line(f"__SM_DONE__ {'0' * len(request_id)} 0\n")


@pytest.mark.asyncio
async def test_persistent_batch_transport_starts_lazily_and_reuses_session_for_same_alias():
    created_processes = []

    async def _factory(alias: str):
        process = _FakeProcess([_success_response("alpha\n"), _success_response("beta\n")])
        created_processes.append((alias, process))
        return process

    transport = PersistentBatchTransport(process_factory=_factory)

    first = await transport.run("srv-a", "echo alpha", timeout_seconds=1.0)
    second = await transport.run("srv-a", "echo beta", timeout_seconds=1.0)

    assert len(created_processes) == 1
    assert first.stdout == "alpha\n"
    assert second.stdout == "beta\n"


@pytest.mark.asyncio
async def test_persistent_batch_transport_recreates_session_after_eof():
    created_processes = []
    processes = [
        _FakeProcess([_eof_response]),
        _FakeProcess([_success_response("recovered\n")]),
    ]

    async def _factory(alias: str):
        process = processes.pop(0)
        created_processes.append((alias, process))
        return process

    transport = PersistentBatchTransport(process_factory=_factory)

    with pytest.raises(PersistentSessionProtocolError, match="before completion marker"):
        await transport.run("srv-a", "echo alpha", timeout_seconds=1.0)

    result = await transport.run("srv-a", "echo beta", timeout_seconds=1.0)

    assert len(created_processes) == 2
    assert created_processes[0][1].killed is True
    assert result.stdout == "recovered\n"


@pytest.mark.asyncio
async def test_persistent_batch_transport_recreates_session_after_timeout():
    created_processes = []
    processes = [
        _FakeProcess([lambda process, request_id: None]),
        _FakeProcess([_success_response("recovered\n")]),
    ]

    async def _factory(alias: str):
        process = processes.pop(0)
        created_processes.append((alias, process))
        return process

    transport = PersistentBatchTransport(process_factory=_factory)

    with pytest.raises(TimeoutError):
        await transport.run("srv-a", "echo alpha", timeout_seconds=0.01)

    result = await transport.run("srv-a", "echo beta", timeout_seconds=1.0)

    assert len(created_processes) == 2
    assert created_processes[0][1].killed is True
    assert result.stdout == "recovered\n"


@pytest.mark.asyncio
async def test_persistent_batch_transport_raises_on_malformed_completion_marker():
    async def _factory(alias: str):
        return _FakeProcess([_malformed_response])

    transport = PersistentBatchTransport(process_factory=_factory)

    with pytest.raises(PersistentSessionProtocolError, match="unexpected completion marker"):
        await transport.run("srv-a", "echo alpha", timeout_seconds=1.0)
