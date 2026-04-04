import asyncio

import pytest

from server_monitor.dashboard.settings import ServerSettings


class _FakeStreamReader:
    def __init__(self, lines: list[str] | None = None):
        self._queue: asyncio.Queue[bytes] = asyncio.Queue()
        for line in lines or []:
            self.feed_line(line)

    async def readline(self) -> bytes:
        return await self._queue.get()

    def feed_line(self, text: str) -> None:
        self._queue.put_nowait(text.encode())

    def feed_eof(self) -> None:
        self._queue.put_nowait(b"")


class _FakeProcess:
    def __init__(
        self, lines: list[str] | None = None, *, close_immediately: bool = False
    ):
        self.stdout = _FakeStreamReader(lines)
        self.killed = False
        self.waited = False
        if close_immediately:
            self.stdout.feed_eof()

    def kill(self) -> None:
        self.killed = True
        self.stdout.feed_eof()

    async def wait(self) -> int:
        self.waited = True
        return 0


@pytest.mark.asyncio
async def test_metrics_stream_manager_starts_one_process_per_server():
    from server_monitor.dashboard.metrics.manager import MetricsStreamManager

    created = []

    async def _factory(alias: str, remote_command: str):
        process = _FakeProcess()
        created.append((alias, remote_command, process))
        return process

    manager = MetricsStreamManager(
        process_factory=_factory,
        on_sample=lambda server_id, sample: None,
        on_state_change=lambda server_id, state: None,
    )

    servers = [
        ServerSettings(
            server_id="srv-a", ssh_alias="server-a", enabled_panels=["system", "gpu"]
        ),
        ServerSettings(
            server_id="srv-b", ssh_alias="server-b", enabled_panels=["system", "gpu"]
        ),
    ]

    await manager.start(servers)
    await asyncio.sleep(0)
    await manager.stop()

    assert [item[0] for item in created] == ["server-a", "server-b"]
    assert all("while :" in item[1] for item in created)


@pytest.mark.asyncio
async def test_metrics_stream_manager_delivers_samples_to_callback():
    from server_monitor.dashboard.metrics.manager import MetricsStreamManager

    samples = []

    async def _factory(alias: str, remote_command: str):
        return _FakeProcess(
            [
                '{"sequence":1,"server_time":"2026-03-12T12:00:00+00:00","sample_interval_ms":250,"cpu_percent":11.0,"memory_percent":22.0,"disk_percent":33.0,"network_rx_kbps":44.0,"network_tx_kbps":55.0,"gpus":[]}\n',
                '{"sequence":2,"server_time":"2026-03-12T12:00:01+00:00","sample_interval_ms":250,"cpu_percent":12.0,"memory_percent":23.0,"disk_percent":33.0,"network_rx_kbps":46.0,"network_tx_kbps":57.0,"gpus":[]}\n',
            ]
        )

    async def _on_sample(server_id: str, sample) -> None:
        samples.append((server_id, sample.sequence))

    manager = MetricsStreamManager(
        process_factory=_factory,
        on_sample=_on_sample,
        on_state_change=lambda server_id, state: None,
    )

    await manager.start(
        [
            ServerSettings(
                server_id="srv-a",
                ssh_alias="server-a",
                enabled_panels=["system", "gpu"],
            )
        ]
    )
    await asyncio.sleep(0.01)
    await manager.stop()

    assert samples == [("srv-a", 1), ("srv-a", 2)]


@pytest.mark.asyncio
async def test_metrics_stream_manager_drops_one_malformed_line_without_restarting():
    from server_monitor.dashboard.metrics.manager import MetricsStreamManager

    created = []
    samples = []
    sleeps = []

    async def _factory(alias: str, remote_command: str):
        process = _FakeProcess(
            [
                '{"sequence":1\n',
                '{"sequence":1,"server_time":"2026-03-12T12:00:00+00:00","sample_interval_ms":250,"cpu_percent":11.0,"memory_percent":22.0,"disk_percent":33.0,"network_rx_kbps":44.0,"network_tx_kbps":55.0,"gpus":[]}\n',
            ]
        )
        created.append(process)
        return process

    async def _on_sample(server_id: str, sample) -> None:
        samples.append((server_id, sample.sequence))

    async def _sleep(delay: float) -> None:
        sleeps.append(delay)

    manager = MetricsStreamManager(
        process_factory=_factory,
        on_sample=_on_sample,
        on_state_change=lambda server_id, state: None,
        sleep_func=_sleep,
    )

    await manager.start(
        [
            ServerSettings(
                server_id="srv-a",
                ssh_alias="server-a",
                enabled_panels=["system", "gpu"],
            )
        ]
    )
    await asyncio.sleep(0.01)
    await manager.stop()

    assert len(created) == 1
    assert samples == [("srv-a", 1)]
    assert sleeps == []


@pytest.mark.asyncio
async def test_metrics_stream_manager_reconnects_after_repeated_parse_failures():
    from server_monitor.dashboard.metrics.manager import MetricsStreamManager

    processes = [
        _FakeProcess(['{"sequence":1\n', '{"sequence":2\n', '{"sequence":3\n']),
        _FakeProcess(
            [
                '{"sequence":4,"server_time":"2026-03-12T12:00:01+00:00","sample_interval_ms":250,"cpu_percent":12.0,"memory_percent":23.0,"disk_percent":33.0,"network_rx_kbps":46.0,"network_tx_kbps":57.0,"gpus":[]}\n'
            ]
        ),
    ]
    created = []
    samples = []
    states = []
    sleeps = []

    async def _factory(alias: str, remote_command: str):
        process = processes.pop(0)
        created.append(process)
        return process

    async def _on_sample(server_id: str, sample) -> None:
        samples.append((server_id, sample.sequence))

    async def _on_state_change(server_id: str, state: str) -> None:
        states.append((server_id, state))

    async def _sleep(delay: float) -> None:
        sleeps.append(delay)

    manager = MetricsStreamManager(
        process_factory=_factory,
        on_sample=_on_sample,
        on_state_change=_on_state_change,
        sleep_func=_sleep,
        reconnect_delays=(1.0,),
        max_parse_failures=3,
    )

    await manager.start(
        [
            ServerSettings(
                server_id="srv-a",
                ssh_alias="server-a",
                enabled_panels=["system", "gpu"],
            )
        ]
    )
    await asyncio.sleep(0.01)
    await manager.stop()

    assert len(created) == 2
    assert sleeps == [1.0]
    assert ("srv-a", "reconnecting") in states
    assert samples == [("srv-a", 4)]


@pytest.mark.asyncio
async def test_metrics_stream_manager_reconnects_after_eof_with_bounded_backoff():
    from server_monitor.dashboard.metrics.manager import MetricsStreamManager

    processes = [
        _FakeProcess(close_immediately=True),
        _FakeProcess(
            [
                '{"sequence":1,"server_time":"2026-03-12T12:00:02+00:00","sample_interval_ms":250,"cpu_percent":13.0,"memory_percent":24.0,"disk_percent":33.0,"network_rx_kbps":47.0,"network_tx_kbps":58.0,"gpus":[]}\n'
            ]
        ),
    ]
    created = []
    sleeps = []
    samples = []

    async def _factory(alias: str, remote_command: str):
        process = processes.pop(0)
        created.append(process)
        return process

    async def _sleep(delay: float) -> None:
        sleeps.append(delay)

    async def _on_sample(server_id: str, sample) -> None:
        samples.append((server_id, sample.sequence))

    manager = MetricsStreamManager(
        process_factory=_factory,
        on_sample=_on_sample,
        on_state_change=lambda server_id, state: None,
        sleep_func=_sleep,
        reconnect_delays=(1.0, 2.0, 5.0),
    )

    await manager.start(
        [
            ServerSettings(
                server_id="srv-a",
                ssh_alias="server-a",
                enabled_panels=["system", "gpu"],
            )
        ]
    )
    await asyncio.sleep(0.01)
    await manager.stop()

    assert len(created) == 2
    assert sleeps == [1.0]
    assert samples == [("srv-a", 1)]


@pytest.mark.asyncio
async def test_metrics_stream_manager_stop_prevents_pending_reconnect_cycle():
    from server_monitor.dashboard.metrics.manager import MetricsStreamManager

    created = []
    sleep_started = asyncio.Event()
    release_sleep = asyncio.Event()

    async def _factory(alias: str, remote_command: str):
        process = _FakeProcess(close_immediately=True)
        created.append(process)
        return process

    async def _sleep(delay: float) -> None:
        sleep_started.set()
        await release_sleep.wait()

    manager = MetricsStreamManager(
        process_factory=_factory,
        on_sample=lambda server_id, sample: None,
        on_state_change=lambda server_id, state: None,
        sleep_func=_sleep,
        reconnect_delays=(1.0,),
    )

    await manager.start(
        [
            ServerSettings(
                server_id="srv-a",
                ssh_alias="server-a",
                enabled_panels=["system", "gpu"],
            )
        ]
    )
    await asyncio.wait_for(sleep_started.wait(), timeout=1.0)
    await manager.stop()
    release_sleep.set()

    assert len(created) == 1


@pytest.mark.asyncio
async def test_create_ssh_process_passes_stream_script_as_single_remote_argument(
    monkeypatch,
):
    from server_monitor.dashboard.metrics.manager import _create_ssh_process

    captured = {}

    async def _fake_create_subprocess_exec(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_create_subprocess_exec)

    await _create_ssh_process("srv-a", "while :; do echo hello; done")

    assert captured["args"] == ("ssh", "srv-a", "while :; do echo hello; done")
