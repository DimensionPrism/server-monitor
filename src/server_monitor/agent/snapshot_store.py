"""In-memory snapshot store for agent data."""

from __future__ import annotations

from datetime import UTC, datetime

from server_monitor.shared.models import ClashStatus, ServerSnapshot


class SnapshotStore:
    """Thread-safe-enough snapshot holder for a single async agent process."""

    def __init__(self, server_id: str) -> None:
        self._snapshot = ServerSnapshot(
            server_id=server_id,
            timestamp=datetime.now(UTC),
            cpu_percent=0,
            memory_percent=0,
            disk_percent=0,
            network_rx_kbps=0,
            network_tx_kbps=0,
            gpus=[],
            repos=[],
            clash=ClashStatus(
                running=False,
                api_reachable=False,
                ui_reachable=False,
                message="not-collected",
            ),
            metadata={},
        )

    @property
    def snapshot(self) -> ServerSnapshot:
        return self._snapshot

    def _replace(self, update: dict) -> None:
        payload = self._snapshot.model_dump()
        payload.update(update)
        self._snapshot = ServerSnapshot.model_validate(payload)

    def update_metrics(self, metrics: dict, *, timestamp: datetime) -> None:
        self._replace(
            {
                "timestamp": timestamp,
                "cpu_percent": metrics["cpu_percent"],
                "memory_percent": metrics["memory_percent"],
                "disk_percent": metrics["disk_percent"],
                "network_rx_kbps": metrics["network_rx_kbps"],
                "network_tx_kbps": metrics["network_tx_kbps"],
                "gpus": metrics.get("gpus", []),
            }
        )

    def update_repos(self, repos: list[dict], *, timestamp: datetime) -> None:
        self._replace(
            {
                "timestamp": timestamp,
                "repos": repos,
            }
        )

    def update_clash(self, clash: dict, *, timestamp: datetime) -> None:
        self._replace(
            {
                "timestamp": timestamp,
                "clash": clash,
            }
        )

    def record_metrics_error(self, error_message: str) -> None:
        metadata = dict(self._snapshot.metadata)
        metadata["metrics_error"] = error_message
        self._snapshot = self._snapshot.model_copy(update={"metadata": metadata})
