from datetime import UTC, datetime


def test_store_retains_last_good_metrics_on_parser_failure():
    from server_monitor.agent.snapshot_store import SnapshotStore

    store = SnapshotStore(server_id="server-a")
    store.update_metrics(
        {
            "cpu_percent": 10.0,
            "memory_percent": 20.0,
            "disk_percent": 30.0,
            "network_rx_kbps": 40.0,
            "network_tx_kbps": 50.0,
            "gpus": [],
        },
        timestamp=datetime(2026, 3, 10, tzinfo=UTC),
    )

    store.record_metrics_error("parse error")
    snapshot = store.snapshot

    assert snapshot.cpu_percent == 10.0
    assert snapshot.memory_percent == 20.0
    assert snapshot.disk_percent == 30.0
    assert snapshot.network_rx_kbps == 40.0
    assert snapshot.network_tx_kbps == 50.0
    assert snapshot.metadata["metrics_error"] == "parse error"
