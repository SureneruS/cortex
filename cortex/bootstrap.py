from __future__ import annotations

import json
import subprocess
from pathlib import Path

from cortex.config import Config
from cortex.state import StateManager


def _run(cmd: list[str], cwd: str | None = None) -> str:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, timeout=15)
        return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return ""


def _get_open_prs(repo_path: str) -> list[dict]:
    raw = _run(
        ["gh", "pr", "list", "--author", "@me", "--state", "open", "--json", "title,number,headRefName"],
        cwd=repo_path,
    )
    if not raw:
        return []
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return []


def _get_active_branches(repo_path: str) -> list[str]:
    raw = _run(["git", "branch", "--list", "--format=%(refname:short)"], cwd=repo_path)
    if not raw:
        return []
    return [b.strip() for b in raw.splitlines() if b.strip() and b.strip() != "main"]


def scan_repos(config: Config, state: StateManager) -> dict:
    stats = {"streams_created": 0, "prs_found": 0, "branches_found": 0, "repos_scanned": 0}

    seen_branches: set[str] = set()

    for repo_name, repo_path_str in config.repos.items():
        repo_path = Path(repo_path_str).expanduser()
        if not repo_path.exists():
            continue
        stats["repos_scanned"] += 1

        prs = _get_open_prs(str(repo_path))
        for pr in prs:
            title = pr.get("title", "")
            number = pr.get("number", "")
            branch = pr.get("headRefName", "")
            seen_branches.add(branch)
            state.create_stream(f"PR #{number}: {title}", [repo_name])
            stats["streams_created"] += 1
            stats["prs_found"] += 1

        branches = _get_active_branches(str(repo_path))
        for branch in branches:
            if branch in seen_branches:
                continue
            stats["branches_found"] += 1

    return stats
