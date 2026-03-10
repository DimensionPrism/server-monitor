import pytest


@pytest.mark.asyncio
async def test_tunnel_reconnect_backoff_after_failure():
    from server_monitor.dashboard.ssh_tunnel import SshTunnelManager

    async def _fail_connect():
        return False

    manager = SshTunnelManager(connect=_fail_connect, base_backoff_seconds=1.0)

    await manager.ensure_connected()

    assert manager.state == "reconnecting"
    assert manager.current_backoff_seconds == 1.0


@pytest.mark.asyncio
async def test_tunnel_connected_on_success():
    from server_monitor.dashboard.ssh_tunnel import SshTunnelManager

    async def _ok_connect():
        return True

    manager = SshTunnelManager(connect=_ok_connect, base_backoff_seconds=1.0)

    await manager.ensure_connected()

    assert manager.state == "connected"
    assert manager.current_backoff_seconds == 0.0
