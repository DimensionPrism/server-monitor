"""Protocol helpers for agentless metrics streaming."""

from __future__ import annotations

from dataclasses import dataclass
import json


@dataclass(slots=True)
class MetricsStreamSample:
    sequence: int
    server_time: str
    sample_interval_ms: int
    cpu_percent: float
    memory_percent: float
    disk_percent: float
    network_rx_kbps: float
    network_tx_kbps: float
    gpus: list[dict]


class MetricsStreamProtocolError(ValueError):
    """Raised when a streamed metrics sample violates the expected schema."""


def parse_metrics_stream_line(line: str) -> MetricsStreamSample:
    """Parse one NDJSON metrics sample line into a validated sample object."""

    try:
        raw = json.loads(line)
    except json.JSONDecodeError as exc:
        raise MetricsStreamProtocolError("malformed JSON") from exc

    if not isinstance(raw, dict):
        raise MetricsStreamProtocolError("sample payload must be an object")

    return MetricsStreamSample(
        sequence=_require_int(raw, "sequence"),
        server_time=_require_str(raw, "server_time"),
        sample_interval_ms=_require_int(raw, "sample_interval_ms"),
        cpu_percent=_require_float(raw, "cpu_percent"),
        memory_percent=_require_float(raw, "memory_percent"),
        disk_percent=_require_float(raw, "disk_percent"),
        network_rx_kbps=_require_float(raw, "network_rx_kbps"),
        network_tx_kbps=_require_float(raw, "network_tx_kbps"),
        gpus=_require_gpu_list(raw, "gpus"),
    )


def _require_int(payload: dict, field_name: str) -> int:
    value = _require_field(payload, field_name)
    if isinstance(value, bool) or not isinstance(value, int):
        raise MetricsStreamProtocolError(f"field '{field_name}' must be an integer")
    return value


def _require_float(payload: dict, field_name: str) -> float:
    value = _require_field(payload, field_name)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MetricsStreamProtocolError(f"field '{field_name}' must be numeric")
    return float(value)


def _require_str(payload: dict, field_name: str) -> str:
    value = _require_field(payload, field_name)
    if not isinstance(value, str):
        raise MetricsStreamProtocolError(f"field '{field_name}' must be a string")
    return value


def _require_gpu_list(payload: dict, field_name: str) -> list[dict]:
    value = _require_field(payload, field_name)
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise MetricsStreamProtocolError(
            f"field '{field_name}' must be a list of objects"
        )
    return value


def _require_field(payload: dict, field_name: str):
    if field_name not in payload:
        raise MetricsStreamProtocolError(f"missing required field '{field_name}'")
    return payload[field_name]
