"""Launch a local terminal and open an SSH session in a remote repo directory."""

from __future__ import annotations

from dataclasses import dataclass
import platform
import shlex
import shutil
import subprocess


@dataclass(frozen=True, slots=True)
class LaunchResult:
    ok: bool
    launched_with: str
    detail: str


def _shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def build_remote_shell_command(repo_path: str) -> str:
    return f"cd {_shell_quote(repo_path)} && exec ${{SHELL:-bash}} -il"


def _build_ssh_argv(*, ssh_alias: str, repo_path: str) -> list[str]:
    remote_command = build_remote_shell_command(repo_path)
    return ["ssh", ssh_alias, "-t", remote_command]


def _build_ssh_command_text(*, ssh_alias: str, repo_path: str) -> str:
    argv = _build_ssh_argv(ssh_alias=ssh_alias, repo_path=repo_path)
    return shlex.join(argv)


def _default_spawn(argv: list[str]) -> None:
    subprocess.Popen(argv)  # noqa: S603


def _escape_applescript_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _open_windows(*, ssh_alias: str, repo_path: str, which, spawn) -> LaunchResult:
    ssh_command_text = _build_ssh_command_text(ssh_alias=ssh_alias, repo_path=repo_path)
    if which("wt"):
        argv = ["wt", "new-tab", "powershell", "-NoExit", "-Command", ssh_command_text]
        spawn(argv)
        return LaunchResult(ok=True, launched_with="wt", detail="Opened with Windows Terminal")

    argv = ["cmd", "/c", "start", "", "powershell", "-NoExit", "-Command", ssh_command_text]
    spawn(argv)
    return LaunchResult(ok=True, launched_with="powershell", detail="Opened with PowerShell")


def _open_macos(*, ssh_alias: str, repo_path: str, spawn) -> LaunchResult:
    ssh_command_text = _build_ssh_command_text(ssh_alias=ssh_alias, repo_path=repo_path)
    escaped = _escape_applescript_string(ssh_command_text)
    script = f'tell application "Terminal" to do script "{escaped}"'
    argv = ["osascript", "-e", script]
    spawn(argv)
    return LaunchResult(ok=True, launched_with="Terminal.app", detail="Opened with Terminal.app")


def _open_linux(*, ssh_alias: str, repo_path: str, which, spawn) -> LaunchResult:
    ssh_argv = _build_ssh_argv(ssh_alias=ssh_alias, repo_path=repo_path)
    ssh_command_text = _build_ssh_command_text(ssh_alias=ssh_alias, repo_path=repo_path)

    candidates: list[tuple[str, list[str]]] = [
        ("x-terminal-emulator", ["x-terminal-emulator", "-e", *ssh_argv]),
        ("gnome-terminal", ["gnome-terminal", "--", *ssh_argv]),
        ("konsole", ["konsole", "-e", *ssh_argv]),
        ("xfce4-terminal", ["xfce4-terminal", "--command", ssh_command_text]),
    ]

    for launcher_name, argv in candidates:
        if not which(launcher_name):
            continue
        spawn(argv)
        return LaunchResult(ok=True, launched_with=launcher_name, detail=f"Opened with {launcher_name}")

    raise RuntimeError("no supported terminal launcher found (tried x-terminal-emulator, gnome-terminal, konsole, xfce4-terminal)")


def open_terminal_with_ssh(
    *,
    ssh_alias: str,
    repo_path: str,
    system_name: str | None = None,
    which=shutil.which,
    spawn=_default_spawn,
) -> LaunchResult:
    system = (system_name or platform.system()).strip()
    try:
        if system == "Windows":
            return _open_windows(ssh_alias=ssh_alias, repo_path=repo_path, which=which, spawn=spawn)
        if system == "Darwin":
            return _open_macos(ssh_alias=ssh_alias, repo_path=repo_path, spawn=spawn)
        if system == "Linux":
            return _open_linux(ssh_alias=ssh_alias, repo_path=repo_path, which=which, spawn=spawn)
        raise RuntimeError(f"unsupported host OS '{system}'")
    except OSError as exc:
        raise RuntimeError(f"failed to launch terminal: {exc}") from exc
