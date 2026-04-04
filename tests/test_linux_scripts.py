import contextlib
import os
import shutil
import signal
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
BASH_PATH = shutil.which("bash")
CAN_EXECUTE_LINUX_SHELL_TESTS = os.name == "posix" and BASH_PATH is not None

LINUX_SCRIPTS = [
    "start-dashboard.sh",
    "stop-dashboard.sh",
    "install-dashboard-user-service.sh",
]


def _read_script(name: str) -> str:
    return (SCRIPTS_DIR / name).read_text(encoding="utf-8")


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def _prepare_linux_start_script_fixture(tmp_path: Path) -> tuple[Path, Path]:
    repo_root = tmp_path / "repo"
    scripts_dir = repo_root / "scripts"
    scripts_dir.mkdir(parents=True)
    (repo_root / "logs").mkdir()
    (repo_root / ".venv" / "bin").mkdir(parents=True)

    start_path = scripts_dir / "start-dashboard.sh"
    start_path.write_text(_read_script("start-dashboard.sh"), encoding="utf-8")
    start_path.chmod(0o755)

    return repo_root, start_path


def test_start_dashboard_linux_script_exists_and_runs_uvicorn():
    content = _read_script("start-dashboard.sh")
    assert ".venv/bin/python" in content
    assert "-m" in content
    assert "uvicorn" in content
    assert "server_monitor.dashboard.main:build_dashboard_app" in content
    assert "--factory" in content
    assert "nohup" in content
    assert "logs/dashboard.log" in content


@pytest.mark.skipif(
    not CAN_EXECUTE_LINUX_SHELL_TESTS,
    reason="Linux shell execution tests require POSIX + bash",
)
def test_start_dashboard_linux_script_background_fails_when_process_exits_early(tmp_path):
    repo_root, start_path = _prepare_linux_start_script_fixture(tmp_path)
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    _write_executable(
        fake_bin / "ss",
        """#!/usr/bin/env bash
printf 'State Recv-Q Send-Q Local Address:Port Peer Address:Port\n'
""",
    )
    _write_executable(
        repo_root / ".venv" / "bin" / "python",
        """#!/usr/bin/env bash
if [[ "$1" == "-m" && "$2" == "uvicorn" ]]; then
  exit 1
fi
if [[ "$1" == "-c" ]]; then
  exit 1
fi
exit 1
""",
    )

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
    proc = subprocess.run(
        [BASH_PATH, str(start_path)],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 1
    assert not (repo_root / "logs" / "dashboard.pid").exists()


@pytest.mark.skipif(
    not CAN_EXECUTE_LINUX_SHELL_TESTS,
    reason="Linux shell execution tests require POSIX + bash",
)
def test_start_dashboard_linux_script_background_waits_for_health_check(tmp_path):
    repo_root, start_path = _prepare_linux_start_script_fixture(tmp_path)
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    _write_executable(
        fake_bin / "ss",
        """#!/usr/bin/env bash
printf 'State Recv-Q Send-Q Local Address:Port Peer Address:Port\n'
""",
    )

    health_count_path = tmp_path / "health-check-count.txt"
    _write_executable(
        repo_root / ".venv" / "bin" / "python",
        f"""#!/usr/bin/env bash
if [[ "$1" == "-m" && "$2" == "uvicorn" ]]; then
  sleep 120
  exit 0
fi
if [[ "$1" == "-c" ]]; then
  count=0
  if [[ -f "{health_count_path}" ]]; then
    count=$(cat "{health_count_path}")
  fi
  count=$((count + 1))
  echo "$count" > "{health_count_path}"
  if [[ "$count" -ge 2 ]]; then
    exit 0
  fi
  exit 1
fi
exit 1
""",
    )

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
    proc = subprocess.run(
        [BASH_PATH, str(start_path)],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    pid_path = repo_root / "logs" / "dashboard.pid"
    try:
        assert proc.returncode == 0
        assert health_count_path.exists()
        assert int(health_count_path.read_text(encoding="utf-8").strip()) >= 2
        assert pid_path.exists()
    finally:
        if pid_path.exists():
            with contextlib.suppress(OSError, ProcessLookupError):
                os.kill(int(pid_path.read_text(encoding="utf-8").strip()), signal.SIGTERM)


@pytest.mark.skipif(
    not CAN_EXECUTE_LINUX_SHELL_TESTS,
    reason="Linux shell execution tests require POSIX + bash",
)
def test_start_dashboard_linux_script_fails_for_foreground_when_port_is_busy(tmp_path):
    repo_root, start_path = _prepare_linux_start_script_fixture(tmp_path)

    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    _write_executable(
        fake_bin / "ss",
        """#!/usr/bin/env bash
printf 'State Recv-Q Send-Q Local Address:Port Peer Address:Port\n'
printf 'LISTEN 0 128 127.0.0.1:8080 0.0.0.0:*\n'
""",
    )

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
    proc = subprocess.run(
        [BASH_PATH, str(start_path), "--foreground"],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 1


def test_stop_dashboard_linux_script_exists_and_targets_dashboard_process():
    content = _read_script("stop-dashboard.sh")
    assert "logs/dashboard.pid" in content
    assert "MAINPID" in content
    assert "pkill -f" not in content


@pytest.mark.skipif(
    not CAN_EXECUTE_LINUX_SHELL_TESTS,
    reason="Linux shell execution tests require POSIX + bash",
)
def test_stop_dashboard_linux_script_does_not_use_pattern_kill_fallback(tmp_path):
    repo_root = tmp_path / "repo"
    scripts_dir = repo_root / "scripts"
    scripts_dir.mkdir(parents=True)
    (repo_root / "logs").mkdir()

    stop_path = scripts_dir / "stop-dashboard.sh"
    stop_path.write_text(_read_script("stop-dashboard.sh"), encoding="utf-8")
    stop_path.chmod(0o755)

    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    pkill_calls_path = tmp_path / "pkill-calls.log"
    _write_executable(
        fake_bin / "pkill",
        f"""#!/usr/bin/env bash
printf '%s\n' "$*" >> "{pkill_calls_path}"
exit 0
""",
    )
    _write_executable(
        fake_bin / "pgrep",
        """#!/usr/bin/env bash
exit 0
""",
    )

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
    proc = subprocess.run(
        [BASH_PATH, str(stop_path)],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0
    assert not pkill_calls_path.exists()


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
