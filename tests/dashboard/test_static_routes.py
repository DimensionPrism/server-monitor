from fastapi.testclient import TestClient


def test_root_serves_dashboard_html():
    from server_monitor.dashboard.api import create_dashboard_app
    from server_monitor.dashboard.ws_hub import WebSocketHub

    app = create_dashboard_app(ws_hub=WebSocketHub())
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert "Server A" in response.text
