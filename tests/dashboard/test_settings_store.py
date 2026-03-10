from pathlib import Path


def test_settings_store_round_trip_create_update_delete(tmp_path: Path):
    from server_monitor.dashboard.settings import DashboardSettingsStore, ServerSettings

    path = tmp_path / "servers.toml"
    store = DashboardSettingsStore(path)

    initial = store.load()
    assert initial.servers == []

    store.create_server(
        ServerSettings(
            server_id="srv-a",
            ssh_alias="server-a",
            working_dirs=["/work/repo-a"],
            enabled_panels=["system", "gpu", "git", "clash"],
        )
    )

    after_create = store.load()
    assert len(after_create.servers) == 1
    assert after_create.servers[0].server_id == "srv-a"

    store.update_server(
        "srv-a",
        ServerSettings(
            server_id="srv-a",
            ssh_alias="server-a-new",
            working_dirs=["/work/repo-a", "/work/repo-b"],
            enabled_panels=["system", "git"],
        ),
    )

    after_update = store.load()
    assert after_update.servers[0].ssh_alias == "server-a-new"
    assert after_update.servers[0].working_dirs == ["/work/repo-a", "/work/repo-b"]
    assert after_update.servers[0].enabled_panels == ["system", "git"]

    store.delete_server("srv-a")

    after_delete = store.load()
    assert after_delete.servers == []


def test_settings_store_saves_intervals(tmp_path: Path):
    from server_monitor.dashboard.settings import DashboardSettings, DashboardSettingsStore

    path = tmp_path / "servers.toml"
    store = DashboardSettingsStore(path)

    settings = DashboardSettings(metrics_interval_seconds=2.0, status_interval_seconds=8.0, servers=[])
    store.save(settings)

    loaded = store.load()
    assert loaded.metrics_interval_seconds == 2.0
    assert loaded.status_interval_seconds == 8.0
