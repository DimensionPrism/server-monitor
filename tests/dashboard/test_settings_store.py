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


def test_settings_store_loads_clash_probe_urls_when_present(tmp_path: Path):
    from server_monitor.dashboard.settings import DashboardSettingsStore

    path = tmp_path / "servers.toml"
    path.write_text(
        """
metrics_interval_seconds = 3
status_interval_seconds = 12

[[servers]]
server_id = "srv-a"
ssh_alias = "server-a"
working_dirs = ["/work/repo-a"]
enabled_panels = ["system", "gpu", "git", "clash"]
clash_api_probe_url = "http://127.0.0.1:9091/version"
clash_ui_probe_url = "http://127.0.0.1:9091/ui"
""".strip(),
        encoding="utf-8",
    )
    store = DashboardSettingsStore(path)

    settings = store.load()
    assert settings.servers[0].clash_api_probe_url == "http://127.0.0.1:9091/version"
    assert settings.servers[0].clash_ui_probe_url == "http://127.0.0.1:9091/ui"


def test_settings_store_applies_default_clash_probe_urls_when_missing(tmp_path: Path):
    from server_monitor.dashboard.settings import DashboardSettingsStore

    path = tmp_path / "servers.toml"
    path.write_text(
        """
metrics_interval_seconds = 3
status_interval_seconds = 12

[[servers]]
server_id = "srv-a"
ssh_alias = "server-a"
working_dirs = ["/work/repo-a"]
enabled_panels = ["system", "gpu", "git", "clash"]
""".strip(),
        encoding="utf-8",
    )
    store = DashboardSettingsStore(path)

    settings = store.load()
    assert settings.servers[0].clash_api_probe_url == "http://127.0.0.1:9090/version"
    assert settings.servers[0].clash_ui_probe_url == "http://127.0.0.1:9090/ui"


def test_settings_store_saves_clash_probe_urls(tmp_path: Path):
    from server_monitor.dashboard.settings import DashboardSettingsStore, ServerSettings

    path = tmp_path / "servers.toml"
    store = DashboardSettingsStore(path)

    store.create_server(
        ServerSettings(
            server_id="srv-a",
            ssh_alias="server-a",
            working_dirs=[],
            enabled_panels=["clash"],
            clash_api_probe_url="http://127.0.0.1:9099/version",
            clash_ui_probe_url="http://127.0.0.1:9099/ui",
        )
    )

    written_text = path.read_text(encoding="utf-8")
    assert 'clash_api_probe_url = "http://127.0.0.1:9099/version"' in written_text
    assert 'clash_ui_probe_url = "http://127.0.0.1:9099/ui"' in written_text
