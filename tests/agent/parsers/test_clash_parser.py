from pathlib import Path


def _load(name: str) -> str:
    return (Path(__file__).parents[2] / "fixtures" / "outputs" / name).read_text()


def test_parse_clash_status_fixture():
    from server_monitor.agent.parsers.clash import parse_clash_status

    parsed = parse_clash_status(_load("clash_status.txt"))

    assert parsed["running"] is True
    assert parsed["api_reachable"] is True
    assert parsed["ui_reachable"] is False
    assert parsed["message"] == "healthy"
