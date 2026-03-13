import sys

from server_monitor.dashboard import cli


def test_cli_main_uses_expected_defaults(monkeypatch):
    captured: dict[str, object] = {}

    def fake_run(app_target: str, **kwargs):
        captured["app_target"] = app_target
        captured["kwargs"] = kwargs

    monkeypatch.setattr(cli.uvicorn, "run", fake_run)
    monkeypatch.setattr(sys, "argv", ["server-monitor-dashboard"])

    cli.main()

    assert captured["app_target"] == "server_monitor.dashboard.main:build_dashboard_app"
    assert captured["kwargs"] == {
        "factory": True,
        "host": "127.0.0.1",
        "port": 8080,
        "reload": False,
    }


def test_cli_main_respects_overrides(monkeypatch):
    captured: dict[str, object] = {}

    def fake_run(app_target: str, **kwargs):
        captured["app_target"] = app_target
        captured["kwargs"] = kwargs

    monkeypatch.setattr(cli.uvicorn, "run", fake_run)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "server-monitor-dashboard",
            "--host",
            "0.0.0.0",
            "--port",
            "9091",
            "--reload",
        ],
    )

    cli.main()

    assert captured["app_target"] == "server_monitor.dashboard.main:build_dashboard_app"
    assert captured["kwargs"] == {
        "factory": True,
        "host": "0.0.0.0",
        "port": 9091,
        "reload": True,
    }
