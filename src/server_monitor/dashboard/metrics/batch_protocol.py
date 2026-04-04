"""Helpers for section-delimited batched command output."""

from __future__ import annotations

from dataclasses import dataclass
import shlex


class BatchProtocolError(ValueError):
    """Raised when batched command output cannot be parsed safely."""


@dataclass(slots=True)
class BatchSection:
    kind: str
    target: str
    exit_code: int
    duration_ms: int
    stream: str
    payload: str


def parse_batch_output(output: str, *, token: str) -> list[BatchSection]:
    """Parse batch output framed by BEGIN/END markers."""

    sections: list[BatchSection] = []
    current_meta: dict[str, str] | None = None
    current_lines: list[str] = []

    for raw_line in output.splitlines(keepends=True):
        if raw_line.startswith(f"{token} BEGIN "):
            if current_meta is not None:
                raise BatchProtocolError("nested batch section")
            current_meta = _parse_metadata(
                raw_line[len(f"{token} BEGIN ") :].rstrip("\r\n")
            )
            current_lines = []
            continue

        if raw_line == f"{token} END\n" or raw_line == f"{token} END\r\n":
            if current_meta is None:
                raise BatchProtocolError("unexpected batch end marker")
            sections.append(
                BatchSection(
                    kind=current_meta["kind"],
                    target=current_meta["target"],
                    exit_code=int(current_meta["exit"]),
                    duration_ms=int(current_meta["duration_ms"]),
                    stream=current_meta["stream"],
                    payload="".join(current_lines),
                )
            )
            current_meta = None
            current_lines = []
            continue

        if current_meta is not None:
            current_lines.append(raw_line)

    if current_meta is not None:
        raise BatchProtocolError("unterminated batch section")

    return sections


def build_metrics_batch_command(
    *, token: str, system_command: str, gpu_command: str
) -> str:
    """Build one remote shell command for the system and GPU panels."""

    return " ".join(
        [
            "set +e;",
            _build_section_command(
                token=token, kind="system", target="server", command=system_command
            ),
            _build_section_command(
                token=token, kind="gpu", target="server", command=gpu_command
            ),
        ]
    )


def build_status_batch_command(
    *,
    token: str,
    git_commands: list[tuple[str, str]],
    clash_secret_command: str,
    clash_probe_command: str,
) -> str:
    """Build one remote shell command for git and clash status panels."""

    sections = ["set +e;"]
    for target, command in git_commands:
        sections.append(
            _build_section_command(
                token=token, kind="git_status", target=target, command=command
            )
        )
    sections.append(
        _build_section_command(
            token=token,
            kind="clash_secret",
            target="server",
            command=clash_secret_command,
        )
    )
    sections.append(
        _build_section_command(
            token=token,
            kind="clash_probe",
            target="server",
            command=clash_probe_command,
        )
    )
    return " ".join(sections)


def _parse_metadata(header: str) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for part in header.split():
        key, separator, value = part.partition("=")
        if separator != "=" or key == "" or value == "":
            raise BatchProtocolError("malformed batch metadata")
        metadata[key] = value

    required_keys = {"kind", "target", "exit", "duration_ms", "stream"}
    if not required_keys.issubset(metadata):
        raise BatchProtocolError("missing batch metadata")

    return metadata


def _build_section_command(*, token: str, kind: str, target: str, command: str) -> str:
    stdout_header = shlex.quote(
        f"{token} BEGIN kind={kind} target={target} exit=%s duration_ms=%s stream=stdout\n"
    )
    stderr_header = shlex.quote(
        f"{token} BEGIN kind={kind} target={target} exit=%s duration_ms=%s stream=stderr\n"
    )
    end_marker = shlex.quote(f"{token} END\n")
    return (
        "__sm_out=$(mktemp); "
        "__sm_err=$(mktemp); "
        "__sm_started=$(date +%s%3N 2>/dev/null || echo 0); "
        f'{{ {command}; }} >"$__sm_out" 2>"$__sm_err"; '
        "__sm_exit=$?; "
        '__sm_finished=$(date +%s%3N 2>/dev/null || echo "$__sm_started"); '
        "__sm_duration=$((__sm_finished-__sm_started)); "
        f'printf {stdout_header} "$__sm_exit" "$__sm_duration"; '
        'cat "$__sm_out"; '
        f"printf {end_marker}; "
        'if [ -s "$__sm_err" ]; then '
        f'printf {stderr_header} "$__sm_exit" "$__sm_duration"; '
        'cat "$__sm_err"; '
        f"printf {end_marker}; "
        "fi; "
        'rm -f "$__sm_out" "$__sm_err";'
    )
