from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"


def _read_script(name: str) -> str:
    return (SCRIPTS_DIR / name).read_text(encoding="utf-8")


def test_start_dashboard_script_exists_and_runs_uvicorn():
    content = _read_script("start-dashboard.ps1")
    assert "uv run uvicorn server_monitor.dashboard.main:build_dashboard_app --factory" in content
    assert "Start-Process" in content
    assert "logs\\dashboard.log" in content


def test_stop_dashboard_script_exists_and_targets_dashboard_process():
    content = _read_script("stop-dashboard.ps1")
    assert "Win32_Process" in content
    assert "server_monitor.dashboard.main:build_dashboard_app" in content
    assert "Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue" in content


def test_install_task_script_exists_and_registers_task():
    content = _read_script("install-dashboard-task.ps1")
    assert "Register-ScheduledTask" in content
    assert "New-ScheduledTaskAction" in content
    assert "start-dashboard.ps1" in content
