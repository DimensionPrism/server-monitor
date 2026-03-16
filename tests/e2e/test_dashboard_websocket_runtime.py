import asyncio
import contextlib
import os
import socket
import subprocess
import sys
import time

import httpx
import pytest


def _find_free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_health(port: int, timeout_seconds: float = 6.0) -> None:
    deadline = time.time() + timeout_seconds
    url = f"http://127.0.0.1:{port}/health"
    while time.time() < deadline:
        with contextlib.suppress(Exception):
            response = httpx.get(url, timeout=0.2, trust_env=False)
            if response.status_code == 200:
                return
        time.sleep(0.1)
    raise RuntimeError("dashboard health endpoint did not start in time")


@pytest.mark.asyncio
async def test_uvicorn_websocket_upgrade_works():
    import websockets

    port = _find_free_port()
    env = os.environ.copy()
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "server_monitor.dashboard.main:build_dashboard_app",
            "--factory",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        _wait_for_health(port)
        async with websockets.connect(f"ws://127.0.0.1:{port}/ws") as ws:
            await ws.send("ping")
            await asyncio.sleep(0.05)
    finally:
        proc.terminate()
        with contextlib.suppress(Exception):
            proc.wait(timeout=3)
        if proc.poll() is None:
            proc.kill()
