from __future__ import annotations

import json

import click

from cortex.cli import _error_exit, _json_out, get_container


@click.group()
def pr() -> None:
    """GitHub PR operations."""
    pass


@pr.command("state")
@click.argument("number", type=int)
@click.option("--repo", default=None, help="Repository in owner/repo format")
def pr_state(number: int, repo: str | None) -> None:
    """Get PR state summary."""
    from cortex import github
    try:
        _json_out(github.pr_state(number, repo=repo))
    except Exception as e:
        _error_exit(str(e))


@pr.command("threads")
@click.argument("number", type=int)
@click.option("--repo", default=None, help="Repository in owner/repo format")
def pr_threads(number: int, repo: str | None) -> None:
    """List PR review threads."""
    from cortex import github
    try:
        _json_out(github.pr_threads(number, repo=repo))
    except Exception as e:
        _error_exit(str(e))


@pr.command("checks")
@click.argument("number", type=int)
@click.option("--repo", default=None, help="Repository in owner/repo format")
def pr_checks(number: int, repo: str | None) -> None:
    """Get CI check details for a PR."""
    from cortex import github
    try:
        _json_out(github.pr_checks(number, repo=repo))
    except Exception as e:
        _error_exit(str(e))


@pr.command("react")
@click.argument("number", type=int)
@click.argument("comment_id", type=int)
@click.argument("reaction")
@click.option("--repo", default=None, help="Repository in owner/repo format")
def pr_react(number: int, comment_id: int, reaction: str, repo: str | None) -> None:
    """React to a PR review comment (+1 or -1)."""
    from cortex import github
    try:
        github.pr_react(number, comment_id, reaction, repo=repo)
        _json_out({"ok": True, "reaction": reaction, "comment_id": comment_id})
    except Exception as e:
        _error_exit(str(e))


@pr.command("resolve")
@click.argument("thread_id")
def pr_resolve(thread_id: str) -> None:
    """Resolve a PR review thread."""
    from cortex import github
    try:
        github.pr_resolve(thread_id)
        _json_out({"ok": True, "thread_id": thread_id, "resolved": True})
    except Exception as e:
        _error_exit(str(e))


@pr.command("batch-resolve")
@click.option("--items", required=True, help="JSON array of {comment_id, thread_id, reaction}")
@click.option("--repo", default=None, help="Repository in owner/repo format")
def pr_batch_resolve(items: str, repo: str | None) -> None:
    """React to and resolve multiple PR threads."""
    from cortex import github
    parsed = json.loads(items)
    results = []
    for item in parsed:
        entry: dict = {"comment_id": item["comment_id"], "thread_id": item["thread_id"]}
        try:
            github.pr_react(0, item["comment_id"], item["reaction"], repo=repo)
            entry["reacted"] = True
        except Exception as e:
            entry["react_error"] = str(e)
            entry["reacted"] = False
        try:
            github.pr_resolve(item["thread_id"])
            entry["resolved"] = True
        except Exception as e:
            entry["resolve_error"] = str(e)
            entry["resolved"] = False
        results.append(entry)
    _json_out(results)


@pr.command("reply")
@click.argument("number", type=int)
@click.argument("comment_id", type=int)
@click.option("--body", required=True, help="Reply text")
@click.option("--repo", default=None, help="Repository in owner/repo format")
def pr_reply(number: int, comment_id: int, body: str, repo: str | None) -> None:
    """Reply to a PR review comment."""
    from cortex import github
    try:
        github.pr_reply(number, comment_id, body, repo=repo)
        _json_out({"ok": True, "comment_id": comment_id})
    except Exception as e:
        _error_exit(str(e))


def _parse_pr_ref(pr_ref: str) -> tuple[str, int]:
    """Parse 'owner/repo#123' into (repo, number). Raises click.BadParameter on invalid format."""
    import re
    match = re.match(r"^([^/]+/[^#]+)#(\d+)$", pr_ref)
    if not match:
        raise click.BadParameter(
            f"Invalid PR reference: {pr_ref!r}. Expected format: owner/repo#number (e.g. cercli/recruitment-backend#123)"
        )
    return match.group(1), int(match.group(2))


@pr.command("watch")
@click.argument("pr_ref")
@click.argument("session_id")
@click.option("--message", default=None, help="Custom message for when changes detected")
def pr_watch(pr_ref: str, session_id: str, message: str | None) -> None:
    """Register a session to watch a PR for changes.

    \b
    PR_REF: Full PR reference in owner/repo#number format
            e.g. cercli/recruitment-backend#123
    """
    import os

    from cortex import github

    repo, number = _parse_pr_ref(pr_ref)
    try:
        state = github.pr_state(number, repo=repo)
    except Exception as e:
        _error_exit(f"Failed to fetch PR state for {pr_ref}: {e}")

    watch_config: dict = {"type": "pr", "repo": repo, "number": number, "last_state": state}
    if message:
        watch_config["message"] = message

    session_repo = get_container().sessions
    session_repo.update(
        session_id,
        {"status": "watching", "runtime": "waiting_input", "watch": watch_config},
        trigger="pr-watch",
        actor=os.environ.get("CORTEX_SESSION_NAME"),
    )
    _json_out({"ok": True, "session_id": session_id, "pr": pr_ref, "repo": repo, "number": number, "baseline": state})


@pr.command("watches")
def pr_watches() -> None:
    """List all active PR watches."""
    session_repo = get_container().sessions
    watching = session_repo.list({"status": "watching"})
    if not watching:
        _json_out([])
        return

    results = []
    for s in watching:
        watch = s.get("watch", {})
        entry: dict = {
            "session": s.get("name", s["_id"]),
            "session_id": s["_id"],
            "type": watch.get("type"),
        }
        if watch.get("type") == "pr":
            entry["pr"] = f"{watch.get('repo')}#{watch.get('number')}"
            entry["repo"] = watch.get("repo")
            entry["number"] = watch.get("number")
        elif watch.get("type") == "alarm":
            entry["wake_at"] = watch.get("wake_at")
            entry["message"] = watch.get("message")
        results.append(entry)
    _json_out(results)
