from fastapi.testclient import TestClient


def test_root_serves_dashboard_html():
    from server_monitor.dashboard.api import create_dashboard_app
    from server_monitor.dashboard.ws_hub import WebSocketHub

    app = create_dashboard_app(ws_hub=WebSocketHub())
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert "Server Settings" in response.text
    assert "new-clash-api-probe-url" in response.text
    assert "new-clash-ui-probe-url" in response.text


def test_app_js_includes_safe_git_ops_controls():
    from server_monitor.dashboard.api import create_dashboard_app
    from server_monitor.dashboard.ws_hub import WebSocketHub

    app = create_dashboard_app(ws_hub=WebSocketHub())
    client = TestClient(app)

    response = client.get("/static/app.js")

    assert response.status_code == 200
    assert "data-git-op=\"fetch\"" in response.text
    assert "data-git-op=\"pull\"" in response.text
    assert "data-git-op=\"checkout\"" in response.text


def test_app_js_gpu_panel_supports_runtime_gpu_fields():
    from server_monitor.dashboard.api import create_dashboard_app
    from server_monitor.dashboard.ws_hub import WebSocketHub

    app = create_dashboard_app(ws_hub=WebSocketHub())
    client = TestClient(app)

    response = client.get("/static/app.js")

    assert response.status_code == 200
    assert "utilization_gpu" in response.text
    assert "memory_used_mb" in response.text
    assert "memory_total_mb" in response.text


def test_app_js_git_op_status_includes_stderr_detail():
    from server_monitor.dashboard.api import create_dashboard_app
    from server_monitor.dashboard.ws_hub import WebSocketHub

    app = create_dashboard_app(ws_hub=WebSocketHub())
    client = TestClient(app)

    response = client.get("/static/app.js")

    assert response.status_code == 200
    assert "response.stderr" in response.text


def test_app_js_uses_nested_monitor_sections():
    from server_monitor.dashboard.api import create_dashboard_app
    from server_monitor.dashboard.ws_hub import WebSocketHub

    app = create_dashboard_app(ws_hub=WebSocketHub())
    client = TestClient(app)

    response = client.get("/static/app.js")

    assert response.status_code == 200
    assert "panel-group panel-group-${options.groupClass}" in response.text
    assert 'groupClass: "system"' in response.text
    assert 'groupClass: "gpu"' in response.text
    assert 'groupClass: "git"' in response.text
    assert 'groupClass: "clash"' in response.text
    assert "<details" in response.text


def test_app_js_nested_sections_have_expected_default_open_state():
    from server_monitor.dashboard.api import create_dashboard_app
    from server_monitor.dashboard.ws_hub import WebSocketHub

    app = create_dashboard_app(ws_hub=WebSocketHub())
    client = TestClient(app)

    response = client.get("/static/app.js")

    assert response.status_code == 200
    assert 'renderPanelGroup("System", renderSystemPanel(snapshot), {' in response.text
    assert 'renderPanelGroup("GPU", renderGpuPanel(snapshot), {' in response.text
    assert 'renderPanelGroup("Git", renderGitPanel(update), {' in response.text
    assert 'renderPanelGroup("Clash", renderClashPanel(update.server_id, update.clash || {}), {' in response.text
    assert "summaryBadgeHtml: renderFreshnessBadge(freshness.system)" in response.text
    assert "summaryBadgeHtml: renderFreshnessBadge(freshness.gpu)" in response.text
    assert "summaryBadgeHtml: renderFreshnessBadge(freshness.git)" in response.text
    assert "summaryBadgeHtml: renderFreshnessBadge(freshness.clash)" in response.text


def test_styles_css_has_server_board_and_gpu_autofit_grid_rules():
    from server_monitor.dashboard.api import create_dashboard_app
    from server_monitor.dashboard.ws_hub import WebSocketHub

    app = create_dashboard_app(ws_hub=WebSocketHub())
    client = TestClient(app)

    response = client.get("/static/styles.css")

    assert response.status_code == 200
    assert ".server-board" in response.text
    assert ".server-card" in response.text
    assert ".panel-group" in response.text
    assert "grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));" in response.text


def test_app_js_persists_panel_open_state_on_rerender():
    from server_monitor.dashboard.api import create_dashboard_app
    from server_monitor.dashboard.ws_hub import WebSocketHub

    app = create_dashboard_app(ws_hub=WebSocketHub())
    client = TestClient(app)

    response = client.get("/static/app.js")

    assert response.status_code == 200
    assert "panelOpenState" in response.text
    assert 'addEventListener("toggle"' in response.text
    assert "data-panel-server-id" in response.text
    assert "data-panel-group" in response.text


def test_app_js_displays_last_update_for_panels_and_repos():
    from server_monitor.dashboard.api import create_dashboard_app
    from server_monitor.dashboard.ws_hub import WebSocketHub

    app = create_dashboard_app(ws_hub=WebSocketHub())
    client = TestClient(app)

    response = client.get("/static/app.js")

    assert response.status_code == 200
    assert "Last update:" in response.text
    assert "system_last_updated_at" in response.text
    assert "gpu_last_updated_at" in response.text
    assert "clash.last_updated_at" in response.text
    assert "repo.last_updated_at" in response.text


def test_app_js_renders_freshness_badges_and_removes_stale_header_line():
    from server_monitor.dashboard.api import create_dashboard_app
    from server_monitor.dashboard.ws_hub import WebSocketHub

    app = create_dashboard_app(ws_hub=WebSocketHub())
    client = TestClient(app)

    response = client.get("/static/app.js")

    assert response.status_code == 200
    assert "function renderFreshnessBadge" in response.text
    assert "update.freshness" in response.text
    assert "repo.freshness" in response.text
    assert "stale: ${stale}" not in response.text


def test_styles_css_has_freshness_badge_rules():
    from server_monitor.dashboard.api import create_dashboard_app
    from server_monitor.dashboard.ws_hub import WebSocketHub

    app = create_dashboard_app(ws_hub=WebSocketHub())
    client = TestClient(app)

    response = client.get("/static/styles.css")

    assert response.status_code == 200
    assert ".freshness-badge" in response.text
    assert ".freshness-live" in response.text
    assert ".freshness-cached" in response.text


def test_app_js_wires_clash_probe_url_settings_fields():
    from server_monitor.dashboard.api import create_dashboard_app
    from server_monitor.dashboard.ws_hub import WebSocketHub

    app = create_dashboard_app(ws_hub=WebSocketHub())
    client = TestClient(app)

    response = client.get("/static/app.js")

    assert response.status_code == 200
    assert "clash_api_probe_url" in response.text
    assert "clash_ui_probe_url" in response.text


def test_app_js_wires_clash_ui_tunnel_open_action():
    from server_monitor.dashboard.api import create_dashboard_app
    from server_monitor.dashboard.ws_hub import WebSocketHub

    app = create_dashboard_app(ws_hub=WebSocketHub())
    client = TestClient(app)

    response = client.get("/static/app.js")

    assert response.status_code == 200
    assert "data-clash-open-ui" in response.text
    assert "data-clash-copy-secret" in response.text
    assert "/clash/tunnel/open" in response.text
    assert "auto_login_url" in response.text
