import pytest


@pytest.mark.asyncio
async def test_poller_fetches_all_domains_and_emits_update():
    from server_monitor.dashboard.poller import AgentPoller

    payloads = {
        "/snapshot": {"cpu_percent": 11.0},
        "/repos": [{"path": "/work/repo"}],
        "/clash": {"running": True},
    }

    async def _fetch(path: str):
        return payloads[path]

    updates = []

    async def _on_update(update: dict):
        updates.append(update)

    poller = AgentPoller(server_id="server-a", fetch_json=_fetch, on_update=_on_update)
    await poller.poll_once()

    assert len(updates) == 1
    assert updates[0]["server_id"] == "server-a"
    assert updates[0]["snapshot"]["cpu_percent"] == 11.0
    assert updates[0]["clash"]["running"] is True
