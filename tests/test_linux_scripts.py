import os
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"

LINUX_SCRIPTS = [
    "start-dashboard.sh",
    "stop-dashboard.sh",
    "install-dashboard-user-service.sh",
]


def _read_script(name: str) -> str:
    return (SCRIPTS_DIR / name).read_text(encoding="utf-8")


def test_start_dashboard_linux_script_exists_and_runs_uvicorn():
    content = _read_script("start-dashboard.sh")
    assert ".venv/bin/python" in content
    assert "-m" in content
    assert "uvicorn" in content
    assert "server_monitor.dashboard.main:build_dashboard_app" in content
    assert "--factory" in content
    assert "nohup" in content
    assert "logs/dashboard.log" in content


def test_stop_dashboard_linux_script_exists_and_targets_dashboard_process():
    content = _read_script("stop-dashboard.sh")
    assert "logs/dashboard.pid" in content
    assert "server_monitor.dashboard.main:build_dashboard_app" in content
    assert "pkill -f" in content


def test_install_linux_service_script_exists_and_registers_service():
    content = _read_script("install-dashboard-user-service.sh")
    assert "systemctl --user daemon-reload" in content
    assert "systemctl --user enable" in content
    assert "systemctl --user start" in content
    assert "start-dashboard.sh" in content


def test_linux_scripts_are_executable():
    for name in LINUX_SCRIPTS:
        path = SCRIPTS_DIR / name
        assert os.access(path, os.X_OK), f"{name} is not executable"
