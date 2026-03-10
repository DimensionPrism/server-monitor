from datetime import UTC, datetime

import pytest


class _FakeWebSocket:
    def __init__(self):
        self.messages = []

    async def send_json(self, payload):
        self.messages.append(payload)


@pytest.mark.asyncio
async def test_dashboard_ws_emits_two_server_payload():
    from server_monitor.dashboard.main import emit_dashboard_update
    from server_monitor.dashboard.ws_hub import WebSocketHub

    now = datetime(2026, 3, 10, tzinfo=UTC)
    hub = WebSocketHub()
    ws = _FakeWebSocket()
    await hub.connect(ws)

    await emit_dashboard_update(
        hub=hub,
        server_id="server-a",
        payload={
            "timestamp": now.isoformat(),
            "snapshot": {"cpu_percent": 15.0},
            "repos": [],
            "clash": {"running": True},
        },
        now=now,
    )
    await emit_dashboard_update(
        hub=hub,
        server_id="server-b",
        payload={
            "timestamp": now.isoformat(),
            "snapshot": {"cpu_percent": 25.0},
            "repos": [],
            "clash": {"running": False},
        },
        now=now,
    )

    assert len(ws.messages) == 2
    assert ws.messages[0]["server_id"] == "server-a"
    assert ws.messages[1]["server_id"] == "server-b"
