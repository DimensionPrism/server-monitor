from pathlib import Path


def _load(name: str) -> str:
    return (Path(__file__).parents[2] / "fixtures" / "outputs" / name).read_text()


def test_parse_clash_status_fixture():
    from server_monitor.dashboard.panels.parsers.clash import parse_clash_status

    parsed = parse_clash_status(_load("clash_status.txt"))

    assert parsed["running"] is True
    assert parsed["api_reachable"] is True
    assert parsed["ui_reachable"] is False
    assert parsed["message"] == "healthy"


def test_parse_clash_status_reads_ip_location_when_present():
    from server_monitor.dashboard.panels.parsers.clash import parse_clash_status

    parsed = parse_clash_status(
        "running=true\n"
        "api_reachable=true\n"
        "ui_reachable=true\n"
        "message=ok\n"
        "ip_location=Los Angeles, California, United States (1.2.3.4)\n"
    )

    assert parsed["ip_location"] == "Los Angeles, California, United States (1.2.3.4)"


def test_parse_clash_status_reads_controller_port_when_present():
    from server_monitor.dashboard.panels.parsers.clash import parse_clash_status

    parsed = parse_clash_status(
        "running=true\n"
        "api_reachable=true\n"
        "ui_reachable=true\n"
        "message=ok\n"
        "controller_port=7373\n"
    )

    assert parsed["controller_port"] == "7373"
