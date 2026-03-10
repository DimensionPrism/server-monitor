"""Parsers for Clash status output."""

from __future__ import annotations


def _parse_bool(raw: str) -> bool:
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def parse_clash_status(text: str) -> dict[str, bool | str]:
    """Parse key-value Clash status lines."""

    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or "=" not in line:
            continue
        key, value = line.split("=", maxsplit=1)
        values[key.strip()] = value.strip()

    return {
        "running": _parse_bool(values.get("running", "false")),
        "api_reachable": _parse_bool(values.get("api_reachable", "false")),
        "ui_reachable": _parse_bool(values.get("ui_reachable", "false")),
        "message": values.get("message", ""),
    }

