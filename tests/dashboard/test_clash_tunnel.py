import io

import pytest


class _FakeProcess:
    def __init__(self, *, returncode=None, stderr_text: str = ""):
        self.returncode = returncode
        self.stderr = io.BytesIO(stderr_text.encode())
        self.terminated = False
        self.killed = False
        self.wait_calls = 0

    def terminate(self):
        self.terminated = True
        if self.returncode is None:
            self.returncode = 0

    def kill(self):
        self.killed = True
        if self.returncode is None:
            self.returncode = -9

    async def wait(self):
        self.wait_calls += 1
        if self.returncode is None:
            self.returncode = 0
        return self.returncode


@pytest.mark.asyncio
async def test_clash_tunnel_manager_opens_tunnel_and_returns_local_url():
    from server_monitor.dashboard.clash_tunnel import ClashTunnelManager

    spawn_calls = []
    process = _FakeProcess(returncode=None)

    async def _spawn(argv):
        spawn_calls.append(argv)
        return process

    async def _probe(**_kwargs):
        return True

    manager = ClashTunnelManager(
        spawn=_spawn,
        probe_local_tunnel=_probe,
        find_free_port=lambda: 19100,
        startup_grace_seconds=0.0,
    )

    result = await manager.open_ui_tunnel(
        server_id="server-a",
        ssh_alias="srv-a",
        clash_ui_probe_url="http://127.0.0.1:9090/ui",
    )

    assert result["url"] == "http://127.0.0.1:19100/ui"
    assert result["local_port"] == 19100
    assert result["reused"] is False
    assert spawn_calls[0][0] == "ssh"
    assert "19100:127.0.0.1:9090" in spawn_calls[0]


@pytest.mark.asyncio
async def test_clash_tunnel_manager_reuses_existing_tunnel_for_same_target():
    from server_monitor.dashboard.clash_tunnel import ClashTunnelManager

    spawn_calls = []
    process = _FakeProcess(returncode=None)

    async def _spawn(argv):
        spawn_calls.append(argv)
        return process

    async def _probe(**_kwargs):
        return True

    manager = ClashTunnelManager(
        spawn=_spawn,
        probe_local_tunnel=_probe,
        find_free_port=lambda: 19101,
        startup_grace_seconds=0.0,
    )

    first = await manager.open_ui_tunnel(
        server_id="server-a",
        ssh_alias="srv-a",
        clash_ui_probe_url="http://127.0.0.1:9090/ui",
    )
    second = await manager.open_ui_tunnel(
        server_id="server-a",
        ssh_alias="srv-a",
        clash_ui_probe_url="http://127.0.0.1:9090/ui",
    )

    assert first["reused"] is False
    assert second["reused"] is True
    assert len(spawn_calls) == 1


@pytest.mark.asyncio
async def test_clash_tunnel_manager_restarts_tunnel_when_target_changes():
    from server_monitor.dashboard.clash_tunnel import ClashTunnelManager

    spawn_calls = []
    first_process = _FakeProcess(returncode=None)
    second_process = _FakeProcess(returncode=None)
    queue = [first_process, second_process]

    async def _spawn(argv):
        spawn_calls.append(argv)
        return queue.pop(0)

    async def _probe(**_kwargs):
        return True

    manager = ClashTunnelManager(
        spawn=_spawn,
        probe_local_tunnel=_probe,
        find_free_port=lambda: 19102,
        startup_grace_seconds=0.0,
    )

    await manager.open_ui_tunnel(
        server_id="server-a",
        ssh_alias="srv-a",
        clash_ui_probe_url="http://127.0.0.1:9090/ui",
    )
    await manager.open_ui_tunnel(
        server_id="server-a",
        ssh_alias="srv-a",
        clash_ui_probe_url="http://127.0.0.1:9091/ui",
    )

    assert first_process.terminated is True
    assert len(spawn_calls) == 2


@pytest.mark.asyncio
async def test_clash_tunnel_manager_rejects_invalid_ui_probe_url():
    from server_monitor.dashboard.clash_tunnel import ClashTunnelManager

    async def _spawn(_argv):
        return _FakeProcess(returncode=None)

    async def _probe(**_kwargs):
        return True

    manager = ClashTunnelManager(
        spawn=_spawn,
        probe_local_tunnel=_probe,
        find_free_port=lambda: 19103,
        startup_grace_seconds=0.0,
    )

    with pytest.raises(ValueError):
        await manager.open_ui_tunnel(
            server_id="server-a",
            ssh_alias="srv-a",
            clash_ui_probe_url="not-a-url",
        )


@pytest.mark.asyncio
async def test_clash_tunnel_manager_raises_when_ssh_process_exits_immediately():
    from server_monitor.dashboard.clash_tunnel import ClashTunnelManager

    async def _spawn(_argv):
        return _FakeProcess(returncode=255, stderr_text="connection refused")

    async def _probe(**_kwargs):
        return True

    manager = ClashTunnelManager(
        spawn=_spawn,
        probe_local_tunnel=_probe,
        find_free_port=lambda: 19104,
        startup_grace_seconds=0.0,
    )

    with pytest.raises(RuntimeError):
        await manager.open_ui_tunnel(
            server_id="server-a",
            ssh_alias="srv-a",
            clash_ui_probe_url="http://127.0.0.1:9090/ui",
        )


@pytest.mark.asyncio
async def test_clash_tunnel_manager_restarts_when_reuse_healthcheck_fails():
    from server_monitor.dashboard.clash_tunnel import ClashTunnelManager

    spawn_calls = []
    first_process = _FakeProcess(returncode=None)
    second_process = _FakeProcess(returncode=None)
    queue = [first_process, second_process]
    probe_calls = []

    async def _spawn(argv):
        spawn_calls.append(argv)
        return queue.pop(0)

    async def _probe(**kwargs):
        probe_calls.append(kwargs)
        # first open succeeds; reuse check fails; replacement tunnel check succeeds
        return len(probe_calls) in {1, 3}

    manager = ClashTunnelManager(
        spawn=_spawn,
        probe_local_tunnel=_probe,
        find_free_port=lambda: 19105,
        startup_grace_seconds=0.0,
        healthcheck_retries=1,
    )

    first = await manager.open_ui_tunnel(
        server_id="server-a",
        ssh_alias="srv-a",
        clash_ui_probe_url="http://127.0.0.1:9090/ui",
    )
    second = await manager.open_ui_tunnel(
        server_id="server-a",
        ssh_alias="srv-a",
        clash_ui_probe_url="http://127.0.0.1:9090/ui",
    )

    assert first["reused"] is False
    assert second["reused"] is False
    assert first_process.terminated is True
    assert len(spawn_calls) == 2


@pytest.mark.asyncio
async def test_clash_tunnel_manager_retries_spawn_when_first_probe_fails():
    from server_monitor.dashboard.clash_tunnel import ClashTunnelManager

    spawn_calls = []
    first_process = _FakeProcess(returncode=None)
    second_process = _FakeProcess(returncode=None)
    queue = [first_process, second_process]
    probe_calls = []

    async def _spawn(argv):
        spawn_calls.append(argv)
        return queue.pop(0)

    async def _probe(**kwargs):
        probe_calls.append(kwargs)
        return len(probe_calls) >= 2

    manager = ClashTunnelManager(
        spawn=_spawn,
        probe_local_tunnel=_probe,
        find_free_port=lambda: 19106,
        startup_grace_seconds=0.0,
        healthcheck_retries=1,
    )

    result = await manager.open_ui_tunnel(
        server_id="server-a",
        ssh_alias="srv-a",
        clash_ui_probe_url="http://127.0.0.1:9090/ui",
    )

    assert result["reused"] is False
    assert len(spawn_calls) == 2
    assert first_process.terminated is True


@pytest.mark.asyncio
async def test_clash_tunnel_manager_raises_when_probe_keeps_failing():
    from server_monitor.dashboard.clash_tunnel import ClashTunnelManager

    process_one = _FakeProcess(returncode=None)
    process_two = _FakeProcess(returncode=None)
    queue = [process_one, process_two]

    async def _spawn(_argv):
        return queue.pop(0)

    async def _probe(**_kwargs):
        return False

    manager = ClashTunnelManager(
        spawn=_spawn,
        probe_local_tunnel=_probe,
        find_free_port=lambda: 19107,
        startup_grace_seconds=0.0,
        healthcheck_retries=1,
    )

    with pytest.raises(RuntimeError, match="local probe failed"):
        await manager.open_ui_tunnel(
            server_id="server-a",
            ssh_alias="srv-a",
            clash_ui_probe_url="http://127.0.0.1:9090/ui",
        )

    assert process_one.terminated is True
    assert process_two.terminated is True
