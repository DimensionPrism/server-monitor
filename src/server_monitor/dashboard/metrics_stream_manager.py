"""Lifecycle manager for long-lived agentless metrics streams."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress
import inspect

from server_monitor.dashboard.metrics_stream_command import build_metrics_stream_command
from server_monitor.dashboard.metrics_stream_protocol import MetricsStreamProtocolError, parse_metrics_stream_line


class MetricsStreamManager:
    """Own one long-lived metrics stream task per configured server."""

    def __init__(
        self,
        *,
        process_factory: Callable[[str, str], Awaitable[object]] | None = None,
        on_sample: Callable[[str, object], object] | None = None,
        on_state_change: Callable[[str, str], object] | None = None,
        command_builder: Callable[[], str] | None = None,
        sleep_func: Callable[[float], Awaitable[object]] | None = None,
        reconnect_delays: tuple[float, ...] = (1.0, 2.0, 5.0),
        max_parse_failures: int = 3,
    ) -> None:
        self._process_factory = process_factory or _create_ssh_process
        self._on_sample = on_sample or (lambda server_id, sample: None)
        self._on_state_change = on_state_change or (lambda server_id, state: None)
        self._command_builder = command_builder or build_metrics_stream_command
        self._sleep_func = sleep_func or asyncio.sleep
        self._reconnect_delays = reconnect_delays or (1.0,)
        self._max_parse_failures = max(1, int(max_parse_failures))
        self._tasks: dict[str, asyncio.Task] = {}
        self._processes: dict[str, object] = {}
        self._server_aliases: dict[str, str] = {}
        self._stop_event = asyncio.Event()

    def bind(
        self,
        *,
        on_sample: Callable[[str, object], object] | None = None,
        on_state_change: Callable[[str, str], object] | None = None,
    ) -> None:
        if on_sample is not None:
            self._on_sample = on_sample
        if on_state_change is not None:
            self._on_state_change = on_state_change

    async def start(self, servers) -> None:
        self._stop_event.clear()
        await self.sync_servers(servers)

    async def sync_servers(self, servers) -> None:
        desired_servers = {
            server.server_id: server
            for server in servers
            if "system" in server.enabled_panels or "gpu" in server.enabled_panels
        }

        for server_id in list(self._tasks):
            if server_id not in desired_servers:
                await self._stop_server_task(server_id)

        for server_id, server in desired_servers.items():
            if server_id in self._tasks and self._server_aliases.get(server_id) == server.ssh_alias:
                continue
            if server_id in self._tasks:
                await self._stop_server_task(server_id)
            if self._stop_event.is_set():
                continue
            task = asyncio.create_task(self._run_server(server), name=f"metrics-stream-{server.server_id}")
            self._tasks[server.server_id] = task
            self._server_aliases[server.server_id] = server.ssh_alias

    async def stop(self) -> None:
        self._stop_event.set()
        for server_id in list(self._tasks):
            await self._stop_server_task(server_id)
        self._tasks.clear()
        self._processes.clear()
        self._server_aliases.clear()

    async def _stop_server_task(self, server_id: str) -> None:
        process = self._processes.pop(server_id, None)
        if process is not None:
            process.kill()
        task = self._tasks.pop(server_id, None)
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        self._server_aliases.pop(server_id, None)

    async def _run_server(self, server) -> None:
        try:
            reconnect_attempt = 0
            while not self._stop_event.is_set():
                await _maybe_await(self._on_state_change(server.server_id, "connecting"))
                process = await self._process_factory(server.ssh_alias, self._command_builder())
                self._processes[server.server_id] = process
                should_reconnect = False
                parse_failures = 0
                try:
                    while not self._stop_event.is_set():
                        raw_line = await process.stdout.readline()
                        if raw_line == b"":
                            should_reconnect = True
                            break

                        line = raw_line.decode(errors="replace").strip()
                        if not line:
                            continue

                        try:
                            sample = parse_metrics_stream_line(line)
                        except MetricsStreamProtocolError:
                            parse_failures += 1
                            if parse_failures >= self._max_parse_failures:
                                should_reconnect = True
                                break
                            continue

                        parse_failures = 0
                        reconnect_attempt = 0
                        await _maybe_await(self._on_sample(server.server_id, sample))
                        await _maybe_await(self._on_state_change(server.server_id, "live"))
                finally:
                    self._processes.pop(server.server_id, None)
                    await _close_process(process)

                if self._stop_event.is_set() or not should_reconnect:
                    break

                await _maybe_await(self._on_state_change(server.server_id, "reconnecting"))
                delay = self._reconnect_delays[min(reconnect_attempt, len(self._reconnect_delays) - 1)]
                reconnect_attempt += 1
                await self._sleep_func(delay)
        finally:
            await _maybe_await(self._on_state_change(server.server_id, "stopped"))


async def _close_process(process) -> None:
    process.kill()
    with suppress(Exception):
        await process.wait()


async def _maybe_await(result) -> None:
    if inspect.isawaitable(result):
        await result


async def _create_ssh_process(alias: str, remote_command: str):
    return await asyncio.create_subprocess_exec(
        "ssh",
        alias,
        remote_command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
