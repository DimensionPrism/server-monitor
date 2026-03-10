import pytest


class _FakeWebSocket:
    def __init__(self):
        self.messages = []

    async def send_json(self, payload):
        self.messages.append(payload)


@pytest.mark.asyncio
async def test_ws_hub_broadcasts_to_all_connections():
    from server_monitor.dashboard.ws_hub import WebSocketHub

    hub = WebSocketHub()
    ws1 = _FakeWebSocket()
    ws2 = _FakeWebSocket()

    await hub.connect(ws1)
    await hub.connect(ws2)
    await hub.broadcast({"ok": True})

    assert ws1.messages == [{"ok": True}]
    assert ws2.messages == [{"ok": True}]


@pytest.mark.asyncio
async def test_ws_hub_disconnect_reduces_connection_count():
    from server_monitor.dashboard.ws_hub import WebSocketHub

    hub = WebSocketHub()
    ws1 = _FakeWebSocket()

    await hub.connect(ws1)
    await hub.disconnect(ws1)

    assert hub.connection_count == 0
