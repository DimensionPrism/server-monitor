"""SSH local-forward manager for opening remote Clash UI in browser."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import dataclass
import socket
from urllib.parse import urlparse


@dataclass(slots=True)
class _TunnelHandle:
    server_id: str
    ssh_alias: str
    remote_host: str
    remote_port: int
    local_port: int
    path_and_query: str
    process: asyncio.subprocess.Process


def _parse_clash_ui_probe_url(url: str) -> tuple[str, int, str]:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("clash_ui_probe_url must use http or https")
    if not parsed.hostname:
        raise ValueError("clash_ui_probe_url must include host")
    remote_port = parsed.port or (443 if parsed.scheme == "https" else 80)
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    return parsed.hostname, remote_port, path


def _default_find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


async def _spawn_ssh_process(argv: list[str]) -> asyncio.subprocess.Process:
    return await asyncio.create_subprocess_exec(
        *argv,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )


async def _default_probe_local_tunnel(
    *,
    bind_host: str,
    local_port: int,
    path_and_query: str,
    timeout_seconds: float,
) -> bool:
    """Probe local forwarded endpoint and accept any HTTP response line."""

    path = path_and_query if path_and_query.startswith("/") else f"/{path_and_query}"
    request = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {bind_host}:{local_port}\r\n"
        "Connection: close\r\n"
        "\r\n"
    ).encode()
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(bind_host, local_port),
            timeout=timeout_seconds,
        )
        writer.write(request)
        await writer.drain()
        status_line = await asyncio.wait_for(reader.readline(), timeout=timeout_seconds)
        writer.close()
        with suppress(Exception):
            await writer.wait_closed()
        return status_line.startswith(b"HTTP/")
    except Exception:
        return False


class ClashTunnelManager:
    """Open/reuse per-server SSH local forwards for Clash UI."""

    def __init__(
        self,
        *,
        bind_host: str = "127.0.0.1",
        startup_grace_seconds: float = 0.1,
        connect_timeout_seconds: int = 5,
        healthcheck_timeout_seconds: float = 1.0,
        healthcheck_retries: int = 3,
        find_free_port=_default_find_free_port,
        spawn=_spawn_ssh_process,
        probe_local_tunnel=_default_probe_local_tunnel,
    ) -> None:
        self.bind_host = bind_host
        self.startup_grace_seconds = startup_grace_seconds
        self.connect_timeout_seconds = int(max(1, connect_timeout_seconds))
        self.healthcheck_timeout_seconds = float(max(0.1, healthcheck_timeout_seconds))
        self.healthcheck_retries = int(max(1, healthcheck_retries))
        self._find_free_port = find_free_port
        self._spawn = spawn
        self._probe_local_tunnel = probe_local_tunnel
        self._handles: dict[str, _TunnelHandle] = {}
        self._lock = asyncio.Lock()

    async def open_ui_tunnel(self, *, server_id: str, ssh_alias: str, clash_ui_probe_url: str) -> dict:
        remote_host, remote_port, path_and_query = _parse_clash_ui_probe_url(clash_ui_probe_url)
        async with self._lock:
            existing = self._handles.get(server_id)
            if existing and self._is_reusable(existing, ssh_alias=ssh_alias, remote_host=remote_host, remote_port=remote_port):
                if await self._probe_tunnel(local_port=existing.local_port, path_and_query=existing.path_and_query):
                    return {
                        "url": _build_local_url(self.bind_host, existing.local_port, existing.path_and_query),
                        "local_port": existing.local_port,
                        "reused": True,
                    }
                await _terminate_process(existing.process)
                self._handles.pop(server_id, None)

            if existing is not None:
                await _terminate_process(existing.process)
                self._handles.pop(server_id, None)

            last_failure = "ssh tunnel process exited before tunnel became available"
            for _ in range(2):
                local_port = int(self._find_free_port())
                argv = [
                    "ssh",
                    "-o",
                    "ExitOnForwardFailure=yes",
                    "-o",
                    f"ConnectTimeout={self.connect_timeout_seconds}",
                    "-N",
                    "-L",
                    f"{local_port}:{remote_host}:{remote_port}",
                    ssh_alias,
                ]
                process = await self._spawn(argv)

                if self.startup_grace_seconds > 0:
                    await asyncio.sleep(self.startup_grace_seconds)
                if process.returncode is not None:
                    last_failure = "ssh tunnel process exited before tunnel became available"
                    await _terminate_process(process)
                    continue

                if not await self._probe_tunnel(local_port=local_port, path_and_query=path_and_query):
                    last_failure = "ssh tunnel local probe failed"
                    await _terminate_process(process)
                    continue

                handle = _TunnelHandle(
                    server_id=server_id,
                    ssh_alias=ssh_alias,
                    remote_host=remote_host,
                    remote_port=remote_port,
                    local_port=local_port,
                    path_and_query=path_and_query,
                    process=process,
                )
                self._handles[server_id] = handle
                return {
                    "url": _build_local_url(self.bind_host, local_port, path_and_query),
                    "local_port": local_port,
                    "reused": False,
                }

                # unreachable
            raise RuntimeError(last_failure)

    async def close_all(self) -> None:
        async with self._lock:
            handles = list(self._handles.values())
            self._handles.clear()
        for handle in handles:
            await _terminate_process(handle.process)

    def _is_reusable(self, handle: _TunnelHandle, *, ssh_alias: str, remote_host: str, remote_port: int) -> bool:
        return (
            handle.process.returncode is None
            and handle.ssh_alias == ssh_alias
            and handle.remote_host == remote_host
            and handle.remote_port == remote_port
        )

    async def _probe_tunnel(self, *, local_port: int, path_and_query: str) -> bool:
        for _ in range(self.healthcheck_retries):
            if await self._probe_local_tunnel(
                bind_host=self.bind_host,
                local_port=local_port,
                path_and_query=path_and_query,
                timeout_seconds=self.healthcheck_timeout_seconds,
            ):
                return True
            await asyncio.sleep(0.05)
        return False


def _build_local_url(bind_host: str, local_port: int, path_and_query: str) -> str:
    return f"http://{bind_host}:{local_port}{path_and_query}"


async def _terminate_process(process: asyncio.subprocess.Process, *, timeout_seconds: float = 1.0) -> None:
    if process.returncode is not None:
        return
    process.terminate()
    try:
        await asyncio.wait_for(process.wait(), timeout=timeout_seconds)
    except asyncio.TimeoutError:
        process.kill()
        with suppress(Exception):
            await process.wait()
