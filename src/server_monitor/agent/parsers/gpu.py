"""Parsers for GPU metric command outputs."""

from __future__ import annotations


def parse_gpu_snapshot(text: str) -> list[dict[str, float | int | str | list]]:
    """Parse CSV-like lines from nvidia-smi style output."""

    rows: list[dict[str, float | int | str | list]] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = [item.strip() for item in line.split(",")]
        if len(parts) < 6:
            continue

        rows.append(
            {
                "index": int(parts[0]),
                "name": parts[1],
                "utilization_gpu": float(parts[2]),
                "memory_used_mb": float(parts[3]),
                "memory_total_mb": float(parts[4]),
                "temperature_c": float(parts[5]),
                "processes": [],
            }
        )

    return rows

