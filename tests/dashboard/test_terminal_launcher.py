from server_monitor.dashboard.terminal_launcher import build_remote_shell_command, open_terminal_with_ssh


def test_build_remote_shell_command_quotes_repo_path():
    command = build_remote_shell_command("/work/repo with space")
    assert "cd '/work/repo with space'" in command
    assert "exec ${SHELL:-bash} -il" in command


def test_open_terminal_linux_uses_first_available_launcher():
    calls = []

    def fake_spawn(argv):
        calls.append(argv)
        return None

    result = open_terminal_with_ssh(
        ssh_alias="srv-a",
        repo_path="/work/repo-a",
        system_name="Linux",
        which=lambda name: "/usr/bin/" + name if name == "x-terminal-emulator" else None,
        spawn=fake_spawn,
    )

    assert result.ok is True
    assert result.launched_with == "x-terminal-emulator"
    assert calls and calls[0][0] == "x-terminal-emulator"


def test_open_terminal_windows_wt_uses_direct_ssh_args():
    calls = []

    def fake_spawn(argv):
        calls.append(argv)
        return None

    result = open_terminal_with_ssh(
        ssh_alias="srv-a",
        repo_path="/work/repo-a",
        system_name="Windows",
        which=lambda name: "C:/Windows/System32/wt.exe" if name == "wt" else None,
        spawn=fake_spawn,
    )

    assert result.ok is True
    assert result.launched_with == "wt"
    assert calls
    assert calls[0][:3] == ["wt", "new-tab", "ssh"]
    assert calls[0][3] == "srv-a"
    assert calls[0][4] == "-t"
    assert calls[0][5] == "cd '/work/repo-a' && exec ${SHELL:-bash} -il"
