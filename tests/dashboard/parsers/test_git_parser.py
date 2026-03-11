from pathlib import Path


def _load(name: str) -> str:
    return (Path(__file__).parents[2] / "fixtures" / "outputs" / name).read_text()


def test_parse_repo_status_fixture():
    from server_monitor.dashboard.parsers.git_status import parse_repo_status

    parsed = parse_repo_status(path="/work/repo", porcelain_text=_load("git_porcelain.txt"), last_commit_age_seconds=600)

    assert parsed["branch"] == "main"
    assert parsed["ahead"] == 2
    assert parsed["behind"] == 1
    assert parsed["staged"] == 1
    assert parsed["unstaged"] == 1
    assert parsed["untracked"] == 1
    assert parsed["dirty"] is True
