from __future__ import annotations

import json
import subprocess
from pathlib import Path

from cortex.config import Config
from cortex.services.stream_service import StreamService


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


def scan_repos(config: Config, stream_service: StreamService) -> dict:
    stats = {"streams_created": 0, "streams_skipped": 0, "prs_found": 0, "branches_found": 0, "repos_scanned": 0}

    existing_titles = {s.title for s in stream_service.list_streams(status="all")}
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
            stats["prs_found"] += 1
            stream_title = f"PR #{number}: {title}"
            if stream_title in existing_titles:
                stats["streams_skipped"] += 1
                continue
            stream_service.create_stream(stream_title, [repo_name])
            existing_titles.add(stream_title)
            stats["streams_created"] += 1

        branches = _get_active_branches(str(repo_path))
        for branch in branches:
            if branch in seen_branches:
                continue
            stats["branches_found"] += 1

    return stats
