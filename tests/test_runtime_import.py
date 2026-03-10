import subprocess
import sys


def test_runtime_import_without_pythonpath():
    proc = subprocess.run(
        [sys.executable, "-c", "import server_monitor"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
