import pytest
import httpx
from datetime import UTC, datetime


class _FakeWebSocket:
    def __init__(self):
        self.messages = []

    async def send_json(self, payload):
        self.messages.append(payload)


@pytest.mark.asyncio
async def test_runtime_poll_once_broadcasts_agent_update():
    from server_monitor.dashboard.runtime import DashboardRuntime, PollSource
    from server_monitor.dashboard.ws_hub import WebSocketHub

    def _handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/snapshot":
            return httpx.Response(
                200,
                json={
                    "timestamp": datetime.now(UTC).isoformat(),
                    "cpu_percent": 12.0,
                    "memory_percent": 34.0,
                    "disk_percent": 56.0,
                    "network_rx_kbps": 1.2,
                    "network_tx_kbps": 3.4,
                    "gpus": [],
                },
            )
        if request.url.path == "/repos":
            return httpx.Response(200, json=[{"path": "/work/repo"}])
        if request.url.path == "/clash":
            return httpx.Response(200, json={"running": True})
        return httpx.Response(404)

    hub = WebSocketHub()
    ws = _FakeWebSocket()
    await hub.connect(ws)

    runtime = DashboardRuntime(
        hub=hub,
        sources=[PollSource(server_id="server-a", base_url="http://agent-a")],
        interval_seconds=3.0,
        stale_after_seconds=10.0,
        transport=httpx.MockTransport(_handler),
    )

    await runtime.poll_once()

    assert len(ws.messages) == 1
    payload = ws.messages[0]
    assert payload["server_id"] == "server-a"
    assert payload["snapshot"]["cpu_percent"] == 12.0
    assert payload["clash"]["running"] is True
    assert payload["stale"] is False
