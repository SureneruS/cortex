from __future__ import annotations

import json
import os

import click

from cortex.cli import _error_exit, _json_out, _output, get_container


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
        data = github.pr_state(number, repo=repo)
    except Exception as e:
        _error_exit(str(e))

    def _fmt(d: dict) -> None:
        from cortex.cli.formatters import get_console, print_detail, styled_status, val
        console = get_console()
        fields = [
            ("Title", val(d.get("title"))),
            ("State", styled_status(d.get("state"))),
            ("Author", val(d.get("author"))),
            ("Branch", val(d.get("head"))),
            ("Review", val(d.get("reviewDecision"))),
            ("Mergeable", val(d.get("mergeable"))),
        ]
        if d.get("labels"):
            fields.append(("Labels", ", ".join(d["labels"])))
        print_detail(fields, title=f"PR #{number}")

        checks = d.get("checks", [])
        if checks:
            console.print(f"\n[bold]Checks ({len(checks)}):[/]")
            for c in checks:
                status = c.get("conclusion") or c.get("status", "?")
                icon = "[green]✓[/]" if status == "SUCCESS" else "[red]✗[/]" if status == "FAILURE" else "[yellow]●[/]"
                console.print(f"  {icon} {c.get('name', '?')}")

    _output(data, _fmt)


@pr.command("threads")
@click.argument("number", type=int)
@click.option("--repo", default=None, help="Repository in owner/repo format")
def pr_threads(number: int, repo: str | None) -> None:
    """List PR review threads."""
    from cortex import github
    try:
        data = github.pr_threads(number, repo=repo)
    except Exception as e:
        _error_exit(str(e))

    def _fmt(threads: list[dict]) -> None:
        from cortex.cli.formatters import get_console, truncate
        console = get_console()
        if not threads:
            console.print("No review threads.")
            return
        console.print(f"[bold]Review threads ({len(threads)}):[/]\n")
        for t in threads:
            resolved = "[dim]resolved[/]" if t.get("isResolved") else "[yellow]open[/]"
            path = t.get("path", "?")
            line = t.get("line", "?")
            console.print(f"  [{resolved}] {path}:{line}")
            for c in t.get("comments", [])[:2]:
                author = c.get("author", "?")
                body = truncate(c.get("body", ""), 80)
                console.print(f"    [bold]{author}:[/] {body}")
            if len(t.get("comments", [])) > 2:
                console.print(f"    [dim]+{len(t['comments']) - 2} more[/]")

    _output(data, _fmt)


@pr.command("checks")
@click.argument("number", type=int)
@click.option("--repo", default=None, help="Repository in owner/repo format")
def pr_checks(number: int, repo: str | None) -> None:
    """Get CI check details for a PR."""
    from cortex import github
    try:
        data = github.pr_checks(number, repo=repo)
    except Exception as e:
        _error_exit(str(e))

    def _fmt(checks: list[dict]) -> None:
        from cortex.cli.formatters import get_console
        console = get_console()
        if not checks:
            console.print("No checks found.")
            return
        console.print(f"[bold]CI Checks ({len(checks)}):[/]\n")
        for c in checks:
            conclusion = c.get("conclusion") or c.get("status", "?")
            if conclusion in ("SUCCESS", "success"):
                icon = "[green]✓[/]"
            elif conclusion in ("FAILURE", "failure"):
                icon = "[red]✗[/]"
            elif conclusion in ("PENDING", "pending", "IN_PROGRESS"):
                icon = "[yellow]●[/]"
            else:
                icon = "[dim]?[/]"
            name = c.get("name", "?")
            console.print(f"  {icon} {name}  [dim]{conclusion}[/]")

    _output(data, _fmt)


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
    except Exception as e:
        _error_exit(str(e))
    data = {"ok": True, "reaction": reaction, "comment_id": comment_id}

    def _fmt(d: dict) -> None:
        from cortex.cli.formatters import print_ok
        print_ok(f"Reacted {d['reaction']} on comment {d['comment_id']}")

    _output(data, _fmt)


@pr.command("resolve")
@click.argument("thread_id")
def pr_resolve(thread_id: str) -> None:
    """Resolve a PR review thread."""
    from cortex import github
    try:
        github.pr_resolve(thread_id)
    except Exception as e:
        _error_exit(str(e))
    data = {"ok": True, "thread_id": thread_id, "resolved": True}

    def _fmt(d: dict) -> None:
        from cortex.cli.formatters import print_ok
        print_ok(f"Resolved thread {d['thread_id'][:12]}")

    _output(data, _fmt)


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

    def _fmt(data: list[dict]) -> None:
        from cortex.cli.formatters import get_console
        console = get_console()
        ok = sum(1 for r in data if r.get("resolved"))
        fail = len(data) - ok
        console.print(f"[bold]Batch resolve:[/] {ok} resolved, {fail} failed")
        for r in data:
            icon = "[green]✓[/]" if r.get("resolved") else "[red]✗[/]"
            console.print(f"  {icon} comment {r['comment_id']}")

    _output(results, _fmt)


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
    except Exception as e:
        _error_exit(str(e))
    data = {"ok": True, "comment_id": comment_id}

    def _fmt(d: dict) -> None:
        from cortex.cli.formatters import print_ok
        print_ok(f"Replied to comment {d['comment_id']}")

    _output(data, _fmt)


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
@click.argument("session_id", required=False, default=None)
@click.option("--message", default=None, help="Custom message for when changes detected")
def pr_watch(pr_ref: str, session_id: str | None, message: str | None) -> None:
    """Register a session to watch a PR for changes.

    \b
    PR_REF: Full PR reference in owner/repo#number format
            e.g. cercli/recruitment-backend#123

    SESSION_ID: Cortex session ID (defaults to current session via CORTEX_SESSION_ID)
    """
    if not session_id:
        session_id = os.environ.get("CORTEX_SESSION_ID")
        if not session_id:
            _error_exit("No session_id provided and CORTEX_SESSION_ID not set")

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
        {"status": "idle", "runtime": "waiting_input", "watch": watch_config, "watch_active": True},
        trigger="pr-watch",
        actor=os.environ.get("CORTEX_SESSION_NAME"),
    )
    data = {"ok": True, "session_id": session_id, "pr": pr_ref, "repo": repo, "number": number, "baseline": state}

    def _fmt(d: dict) -> None:
        from cortex.cli.formatters import print_ok
        print_ok(f"Watching {d['pr']} (session: {d['session_id'][:12]})")

    _output(data, _fmt)


@pr.command("watches")
def pr_watches() -> None:
    """List all active PR watches."""
    session_repo = get_container().sessions
    watching = session_repo.list({"watch_active": True})
    if not watching:
        data: list[dict] = []
    else:
        data = []
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
            data.append(entry)

    def _fmt(items: list[dict]) -> None:
        from cortex.cli.formatters import print_table, val
        if not items:
            click.echo("No active watches.")
            return
        cols = [("Session", {}), ("Type", {}), ("Target", {})]
        rows = []
        for w in items:
            target = w.get("pr") or w.get("wake_at") or "—"
            rows.append([val(w.get("session")), val(w.get("type")), target])
        print_table(cols, rows, count=len(items))

    _output(data, _fmt)
