"""Parsers for system metric command outputs."""

from __future__ import annotations


def parse_system_snapshot(text: str) -> dict[str, float]:
    """Parse a simple key-value metrics snapshot."""

    mapping: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", maxsplit=1)
        mapping[key.strip().upper()] = value.strip()

    return {
        "cpu_percent": float(mapping.get("CPU", 0.0)),
        "memory_percent": float(mapping.get("MEM", 0.0)),
        "disk_percent": float(mapping.get("DISK", 0.0)),
        "network_rx_kbps": float(mapping.get("RX_KBPS", 0.0)),
        "network_tx_kbps": float(mapping.get("TX_KBPS", 0.0)),
    }

