"""Parsers for git status outputs."""

from __future__ import annotations

import re


BRANCH_LINE = re.compile(r"^##\s+(?P<branch>[^\.\s]+)")
AHEAD_RE = re.compile(r"ahead\s+(\d+)")
BEHIND_RE = re.compile(r"behind\s+(\d+)")


def parse_repo_status(
    *,
    path: str,
    porcelain_text: str,
    last_commit_age_seconds: int,
) -> dict[str, str | int | bool]:
    """Parse `git status --porcelain --branch` output."""

    branch = "unknown"
    ahead = 0
    behind = 0
    staged = 0
    unstaged = 0
    untracked = 0

    lines = porcelain_text.splitlines()
    for line in lines:
        if line.startswith("##"):
            branch_match = BRANCH_LINE.search(line)
            if branch_match:
                branch = branch_match.group("branch")
            ahead_match = AHEAD_RE.search(line)
            if ahead_match:
                ahead = int(ahead_match.group(1))
            behind_match = BEHIND_RE.search(line)
            if behind_match:
                behind = int(behind_match.group(1))
            continue

        if line.startswith("??"):
            untracked += 1
            continue

        if len(line) >= 2:
            if line[0] != " ":
                staged += 1
            if line[1] != " ":
                unstaged += 1

    return {
        "path": path,
        "branch": branch,
        "dirty": (staged + unstaged + untracked) > 0,
        "ahead": ahead,
        "behind": behind,
        "staged": staged,
        "unstaged": unstaged,
        "untracked": untracked,
        "last_commit_age_seconds": last_commit_age_seconds,
    }
