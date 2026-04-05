from __future__ import annotations

import json
import time
from pathlib import Path

import click

from cortex.cli import _cli_log, _error_exit, _json_out, _output, get_container
from cortex.services.session_service import ClosePermissionDenied, SessionNotFound, SpawnDenied


@click.group()
def session() -> None:
    """Manage Claude Code sessions."""
    pass


def _svc():
    return get_container().session_service


def _repo():
    return get_container().sessions


def _caller() -> str | None:
    import os
    return os.environ.get("CORTEX_SESSION_NAME")


def _resolve_or_exit(ref: str) -> dict:
    svc = _svc()
    try:
        return svc.resolve(ref)
    except (SessionNotFound, ValueError) as e:
        _error_exit(str(e))


# ── Spawn ────────────────────────────────────────────────────


@session.command()
@click.option("--name", required=True, help="Session name")
@click.option("--goal", default=None, help="Registry metadata describing the session's purpose")
@click.option("--prompt", default=None, help="Prompt to send to the session after it starts")
@click.option("--workspace", default="default", help="Workspace (default or background)")
@click.option("--model", default=None, help="Claude model (e.g. haiku, sonnet, opus)")
@click.option("--split", is_flag=True, default=False, help="Split current pane horizontally instead of new tab")
@click.option("--resume", "resume_id", default=None, help="CC session UUID to resume")
@click.option("--repo", default=None, help="Repo name under ~/workspace/cercli/ to use as cwd")
@click.option("--permission-mode", default=None, help="CC permission mode (e.g. plan, full)")
@click.option("--effort", default=None, help="CC effort level (e.g. low, medium, high)")
@click.option("--agent", "agent_name", default=None, help="CC agent name to use")
@click.option("--allowed-tools", default=None, help="CC allowed tools (comma-separated)")
@click.option("--worktree", default=None, help="CC worktree name")
@click.option("--beside", default=None, help="Split horizontally beside this session/pane")
@click.option("--below", default=None, help="Split vertically below this session/pane")
@click.option("--color", default=None, help="CC session color")
@click.option("--command", "custom_command", default=None, hidden=True, help="Override the claude command")
def spawn(
    name: str,
    goal: str | None,
    prompt: str | None,
    workspace: str,
    model: str | None,
    split: bool,
    resume_id: str | None,
    repo: str | None,
    permission_mode: str | None,
    effort: str | None,
    agent_name: str | None,
    allowed_tools: str | None,
    worktree: str | None,
    beside: str | None,
    below: str | None,
    color: str | None,
    custom_command: str | None,
) -> None:
    """Spawn a new Claude Code session in a tmux pane."""
    log = _cli_log()
    log.info("CLI spawn called", name=name, goal=bool(goal), prompt=bool(prompt), workspace=workspace)

    repo_path: Path | None = None
    if repo:
        repo_path = Path.home() / "workspace" / "cercli" / repo
        if not repo_path.is_dir():
            _error_exit(f"Repo directory not found: {repo_path}")
        if not (repo_path / ".git").exists():
            _error_exit(f"Not a git repo (no .git): {repo_path}")

    if split and not beside and not below:
        beside_pane = _resolve_caller_pane()
        if beside_pane:
            beside = beside_pane

    try:
        result = _svc().spawn(
            name=name,
            goal=goal,
            prompt=prompt,
            workspace=workspace,
            model=model,
            resume_id=resume_id,
            repo_path=repo_path,
            permission_mode=permission_mode,
            effort=effort,
            agent_name=agent_name,
            allowed_tools=allowed_tools,
            worktree=worktree,
            beside=beside,
            below=below,
            color=color,
            custom_command=custom_command,
        )
    except (ValueError, SpawnDenied) as e:
        _error_exit(str(e))

    def _fmt(data: dict) -> None:
        from cortex.cli.formatters import print_detail, styled_status, val
        fields = [
            ("Name", val(data.get("name"))),
            ("ID", val(data.get("session_id"))),
            ("Status", styled_status(data.get("status"))),
            ("Pane", val(data.get("pane_id"))),
        ]
        if data.get("workspace"):
            fields.append(("Workspace", val(data["workspace"])))
        print_detail(fields, title="Session spawned")

    _output(result, _fmt)


def _resolve_caller_pane() -> str | None:
    import os
    caller_id = os.environ.get("CORTEX_SESSION_ID")
    if not caller_id:
        return None
    doc = _repo().get(caller_id)
    if doc and doc.get("pane_id"):
        return str(doc["pane_id"])
    return None


# ── List / Get / Register / Update ──────────────────────────


def _fmt_session_detail(doc: dict) -> None:
    from cortex.cli.formatters import (
        get_console, print_detail, relative_time, styled_runtime, styled_status, truncate, val,
    )
    fields = [
        ("Name", val(doc.get("name"))),
        ("ID", val(doc.get("_id"))),
        ("Status", styled_status(doc.get("status"))),
        ("Runtime", styled_runtime(doc.get("runtime"))),
        ("Role", val(doc.get("role"))),
        ("Workspace", val(doc.get("workspace"))),
        ("Pane", val(doc.get("pane_id"))),
        ("Created", relative_time(doc.get("created_at"))),
    ]
    if doc.get("goal"):
        fields.append(("Goal", truncate(doc["goal"], 100)))
    if doc.get("spawned_by"):
        fields.append(("Spawned by", val(doc["spawned_by"])))
    if doc.get("repos"):
        fields.append(("Repos", ", ".join(doc["repos"])))
    if doc.get("model"):
        fields.append(("Model", val(doc["model"])))
    if doc.get("color"):
        fields.append(("Color", val(doc["color"])))
    if doc.get("cc_version"):
        fields.append(("CC version", val(doc["cc_version"])))
    if doc.get("last_error"):
        err = doc["last_error"]
        fields.append(("Last error", f"{err.get('type', '?')}: {truncate(str(err.get('details', '')), 80)}"))
    if doc.get("watch"):
        w = doc["watch"]
        if w.get("type") == "pr":
            fields.append(("Watch", f"PR {w.get('repo')}#{w.get('number')}"))
        elif w.get("type") == "alarm":
            fields.append(("Watch", f"Alarm at {w.get('wake_at')}"))
    print_detail(fields, title=val(doc.get("name"), "Session"))


def _fmt_lifecycle_ok(action: str):
    def _fmt(data: dict) -> None:
        from cortex.cli.formatters import print_ok, styled_status, val
        name = val(data.get("name", data.get("_id")))
        status = data.get("status", action)
        print_ok(f"Session {action}: {name} [{styled_status(status)}]")
    return _fmt


def _fmt_session_list_row(s: dict) -> list[str]:
    from cortex.cli.formatters import relative_time, styled_runtime, styled_status, val
    return [
        val(s.get("name")),
        styled_status(s.get("status")),
        styled_runtime(s.get("runtime")),
        val(s.get("role")),
        relative_time(s.get("created_at")),
        val(s.get("_id", ""), "")[:12],
    ]


@session.command("list")
@click.option("--status", "filter_status", default=None, help="Filter by status")
@click.option("--runtime", "filter_runtime", default=None, help="Filter by runtime state")
@click.option("--all", "show_all", is_flag=True, default=False, help="Include completed/closed sessions")
@click.option("--brief", is_flag=True, default=False, help="Omit events and watch details")
@click.option("--limit", "limit", type=int, default=None, help="Max sessions to return")
def list_sessions(
    filter_status: str | None,
    filter_runtime: str | None,
    show_all: bool,
    brief: bool,
    limit: int | None,
) -> None:
    """List registered sessions. Shows non-terminal sessions by default."""
    from cortex.domain.session_states import TERMINAL

    repo = _repo()
    filters = {}
    if filter_status:
        filters["status"] = filter_status
    elif not show_all:
        filters["status"] = {"$nin": [s.value for s in TERMINAL]}
    if filter_runtime:
        filters["runtime"] = filter_runtime
    sessions = repo.list(filters, brief=brief, limit=limit)

    def _fmt(data: list[dict]) -> None:
        from cortex.cli.formatters import print_table, relative_time, styled_runtime, styled_status, val
        if not data:
            click.echo("No sessions found.")
            return
        cols = [
            ("Name", {}),
            ("Status", {}),
            ("Runtime", {}),
            ("Role", {}),
            ("Age", {"justify": "right"}),
            ("ID", {"style": "dim"}),
        ]
        rows = []
        for s in data:
            rows.append([
                val(s.get("name")),
                styled_status(s.get("status")),
                styled_runtime(s.get("runtime")),
                val(s.get("role")),
                relative_time(s.get("created_at")),
                val(s.get("_id", ""), "")[:12],
            ])
        print_table(cols, rows, count=len(data))

    _output(sessions, _fmt)


@session.command()
@click.argument("session_id")
def get(session_id: str) -> None:
    """Get a session by ID, name, or ID prefix."""
    doc = _resolve_or_exit(session_id)
    _output(doc, _fmt_session_detail)


@session.command()
@click.argument("ref")
@click.option("--all", "include_dead", is_flag=True, help="Include completed/dead children")
def children(ref: str, include_dead: bool) -> None:
    """List direct child sessions spawned by a session."""
    try:
        result = _svc().children(ref, include_dead=include_dead)
    except (SessionNotFound, ValueError) as e:
        _error_exit(str(e))

    def _fmt(data: list[dict]) -> None:
        from cortex.cli.formatters import print_table
        if not data:
            click.echo("No child sessions.")
            return
        cols = [("Name", {}), ("Status", {}), ("Runtime", {}), ("Role", {}), ("Age", {"justify": "right"}), ("ID", {"style": "dim"})]
        print_table(cols, [_fmt_session_list_row(s) for s in data], count=len(data))

    _output(result, _fmt)


@session.command()
@click.argument("ref", required=False)
def tree(ref: str | None) -> None:
    """Show session hierarchy as a tree."""
    try:
        result = _svc().tree(ref)
    except (SessionNotFound, ValueError) as e:
        _error_exit(str(e))

    def _fmt(data: dict | list) -> None:
        from cortex.cli.formatters import get_console, styled_status, val
        console = get_console()

        def _print_node(node: dict, indent: int = 0) -> None:
            prefix = "  " * indent + ("├─ " if indent > 0 else "")
            name = val(node.get("name"))
            status = styled_status(node.get("status"))
            console.print(f"{prefix}{name} [{status}]")
            for child in node.get("children", []):
                _print_node(child, indent + 1)

        if isinstance(data, list):
            for node in data:
                _print_node(node)
        else:
            _print_node(data)

    _output(result, _fmt)


@session.command()
@click.option("--data", required=True, help="JSON object of fields to set on the new session")
@click.option("--id", "session_id", default=None, help="Use a specific ID")
def register(data: str, session_id: str | None) -> None:
    """Register a new session in the Cortex registry."""
    log = _cli_log()
    try:
        fields = json.loads(data)
    except json.JSONDecodeError as e:
        _error_exit(f"Invalid JSON: {e}")
    doc = _repo().register(session_id, fields)
    log.info("Session registered", session_id=doc["_id"])
    _output(doc, lambda d: _fmt_session_detail(d))


@session.command()
@click.argument("session_id")
@click.option("--data", required=True, help="JSON object of fields to merge")
@click.option("--trigger", default="update", help="What triggered this update")
@click.option("--increment", default=None, help="Field name to atomically increment by 1")
def update(session_id: str, data: str, trigger: str, increment: str | None) -> None:
    """Update a session's fields."""
    log = _cli_log()
    try:
        fields = json.loads(data)
    except json.JSONDecodeError as e:
        _error_exit(f"Invalid JSON: {e}")
    doc = _resolve_or_exit(session_id)
    inc = {increment: 1} if increment else None
    try:
        result = _repo().update(doc["_id"], fields, trigger=trigger, actor=_caller(), increment=inc)
    except ValueError as e:
        _error_exit(str(e))
    log.info("Session updated", session_id=doc["_id"])

    def _fmt(data: dict) -> None:
        from cortex.cli.formatters import print_ok, val
        print_ok(f"Session updated: {val(data.get('name', data.get('_id')))}")

    _output(result, _fmt)


@session.command("link-cc")
@click.argument("session_id")
@click.argument("cc_session_id")
@click.option("--data", default=None, help="JSON object of extra fields for the cc_sessions entry")
def link_cc(session_id: str, cc_session_id: str, data: str | None) -> None:
    """Link a new CC session ID (appends to cc_sessions array)."""
    log = _cli_log()
    doc = _resolve_or_exit(session_id)
    extra = None
    if data:
        try:
            extra = json.loads(data)
        except json.JSONDecodeError as e:
            _error_exit(f"Invalid JSON: {e}")
    result = _repo().append_cc_session(doc["_id"], cc_session_id, extra=extra)
    if result is None:
        _error_exit(f"Session not found: {session_id}")
    log.info("CC session linked", session_id=doc["_id"], cc_session_id=cc_session_id)

    def _fmt(data: dict) -> None:
        from cortex.cli.formatters import print_ok, val
        print_ok(f"CC session linked: {cc_session_id[:12]} → {val(data.get('name', data.get('_id')))}")

    _output(result, _fmt)


# ── Message ──────────────────────────────────────────────────


@session.command()
@click.argument("session_name")
@click.argument("content")
@click.option("--thread-id", default=None, help="Thread ID for conversation linking")
@click.option("--meta", "meta_json", default=None, help="JSON object of extra meta fields")
def message(session_name: str, content: str, thread_id: str | None, meta_json: str | None) -> None:
    """Send a message to a session via channels."""
    extra_meta = None
    if meta_json:
        try:
            extra_meta = json.loads(meta_json)
        except json.JSONDecodeError as e:
            _error_exit(f"Invalid --meta JSON: {e}")
    try:
        result = _svc().send_message(session_name, content, thread_id=thread_id, extra_meta=extra_meta)
    except SessionNotFound as e:
        _error_exit(str(e))

    def _fmt(data: dict) -> None:
        from cortex.cli.formatters import print_ok, val
        print_ok(f"Message {val(data.get('status'), 'sent')} → {session_name}")

    _output(result, _fmt)


@session.command()
@click.argument("session_name", required=False, default=None)
@click.option("--to", "to_filter", default=None, help="Filter by recipient")
@click.option("--limit", "limit_count", type=int, default=20, help="Max messages")
def messages(session_name: str | None, to_filter: str | None, limit_count: int) -> None:
    """View recent inter-session messages."""
    msgs = get_container().messages.list_messages(
        session_name=session_name, to_filter=to_filter, limit=limit_count
    )
    msg_dicts = [
        {"sender": m.sender, "recipient": m.recipient, "content": m.content,
         "status": m.status, "type": (m.meta or {}).get("type"), "created_at": m.created_at}
        for m in (msgs or [])
    ]

    def _fmt(data: list[dict]) -> None:
        from cortex.cli.formatters import get_console, relative_time, truncate
        if not data:
            click.echo("No messages found.")
            return
        console = get_console()
        for m in reversed(data):
            age = relative_time(m.get("created_at"))
            msg_type = m.get("type") or "?"
            preview = truncate(m.get("content", ""), 100)
            console.print(
                f"  [dim]{age:>8}[/]  [bold]{m['sender']}[/] → {m['recipient']}"
                f"  [dim]({msg_type})[/]  {preview}"
            )
        console.print(f"[dim]{len(data)} message(s)[/]")

    _output(msg_dicts, _fmt)


# ── Lifecycle ────────────────────────────────────────────────


@session.command()
@click.argument("session_id")
def attach(session_id: str) -> None:
    """Jump to a session's tmux pane."""
    try:
        _svc().attach(session_id)
    except (SessionNotFound, ValueError) as e:
        _error_exit(str(e))


@session.command()
@click.argument("session_id")
@click.option("--lines", default=50, help="Number of scrollback lines to capture")
def capture(session_id: str, lines: int) -> None:
    """Capture terminal output from a session's tmux pane."""
    try:
        result = _svc().capture(session_id, lines=lines)
    except (SessionNotFound, ValueError) as e:
        _error_exit(str(e))

    def _fmt(data: dict) -> None:
        text = data.get("output", "")
        if text:
            click.echo(text)
        else:
            click.echo("(empty)")

    _output(result, _fmt)


@session.command()
@click.argument("session_id")
@click.option("--force", is_flag=True, help="Skip wrapup and close immediately")
@click.option("--cascade", is_flag=True, help="Also close all descendant sessions")
@click.option("--from-hook", is_flag=True, hidden=True, help="Called from SessionEnd hook (skip /exit signal)")
def close(session_id: str, force: bool, cascade: bool, from_hook: bool) -> None:
    """Close a session — expire messages, update registry, signal exit."""
    log = _cli_log()
    log.info("CLI session close called", session_id=session_id, force=force, cascade=cascade, from_hook=from_hook)
    try:
        doc = _svc().close(session_id, force=force, cascade=cascade, from_hook=from_hook)
    except (SessionNotFound, ValueError, ClosePermissionDenied) as e:
        _error_exit(str(e))
    _output(doc, _fmt_lifecycle_ok("closed"))


@session.command()
@click.argument("session_id")
def wrapup(session_id: str) -> None:
    """Run wrapup routine on a session (memorize, save tasks, etc.)."""
    try:
        ok = _svc().wrapup(session_id)
    except (SessionNotFound, ValueError) as e:
        _error_exit(str(e))
    def _fmt(data: dict) -> None:
        from cortex.cli.formatters import print_ok
        print_ok(f"Wrapup {'complete' if data.get('ok') else 'skipped'}: {session_id}")

    _output({"ok": ok, "session_id": session_id}, _fmt)


@session.command("auto-close")
@click.argument("pane_id")
def auto_close(pane_id: str) -> None:
    """Close a session by its tmux pane_id (used by tmux hooks)."""
    log = _cli_log()
    log.info("CLI auto-close called", pane_id=pane_id)
    repo = _repo()
    sessions = repo.list({"status": {"$nin": ["completed", "closed"]}, "pane_id": pane_id})
    if not sessions:
        _error_exit(f"No active session for pane {pane_id}")
    doc = sessions[0]
    result = repo.close(doc["_id"], trigger="auto-close", actor="tmux-hook")
    log.info("Auto-closed session", session_id=doc["_id"])
    _output(result, _fmt_lifecycle_ok("auto-closed"))


@session.command()
@click.argument("session_id")
def pause(session_id: str) -> None:
    """Pause a session — sends /exit, preserves cc_session_id for resume."""
    try:
        doc = _svc().pause(session_id)
    except (SessionNotFound, ValueError) as e:
        _error_exit(str(e))
    _output(doc, _fmt_lifecycle_ok("paused"))


@session.command()
@click.argument("session_id")
def resume(session_id: str) -> None:
    """Resume a paused session."""
    try:
        doc = _svc().resume(session_id)
    except (SessionNotFound, ValueError) as e:
        _error_exit(str(e))
    _output(doc, _fmt_lifecycle_ok("resumed"))


@session.command()
@click.argument("session_id")
def hide(session_id: str) -> None:
    """Move a session to the background workspace."""
    try:
        doc = _svc().hide(session_id)
    except (SessionNotFound, ValueError, RuntimeError) as e:
        _error_exit(str(e))
    _output(doc, _fmt_lifecycle_ok("hidden"))


@session.command()
@click.argument("session_id")
def show(session_id: str) -> None:
    """Bring a hidden session back from background."""
    try:
        doc = _svc().show(session_id)
    except (SessionNotFound, ValueError, RuntimeError) as e:
        _error_exit(str(e))
    _output(doc, _fmt_lifecycle_ok("shown"))


@session.command()
@click.argument("session_id")
def restart(session_id: str) -> None:
    """Restart CC — pause then resume with new CC version."""
    import subprocess

    log = _cli_log()
    result = subprocess.run(
        ["cortex", "--json", "session", "pause", session_id],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        _error_exit(f"Pause failed: {result.stdout}")

    result = subprocess.run(
        ["cortex", "--json", "session", "resume", session_id],
        capture_output=True, text=True, timeout=15,
    )
    if result.returncode != 0:
        _error_exit(f"Resume failed: {result.stdout}")

    doc = json.loads(result.stdout)
    log.info("Session restarted", session_id=session_id)
    _output(doc, _fmt_lifecycle_ok("restarted"))


# ── Health / Cleanup ─────────────────────────────────────────


@session.command()
def health() -> None:
    """Comprehensive health check."""
    result = _svc().health_check()

    def _fmt(data: dict) -> None:
        from cortex.cli.formatters import get_console, styled_status
        console = get_console()
        summary = data.get("summary", {})
        console.print(f"[bold]Health Check[/]")
        for key, val in summary.items():
            console.print(f"  {key}: {val}")
        issues = data.get("issues", [])
        if issues:
            console.print(f"\n[yellow]Issues ({len(issues)}):[/]")
            for issue in issues:
                console.print(f"  [yellow]![/] {issue}")
        else:
            console.print(f"\n[green]No issues found.[/]")
        sessions = data.get("sessions", [])
        if sessions:
            console.print(f"\n[bold]Sessions ({len(sessions)}):[/]")
            for s in sessions:
                name = s.get("name", "?")
                status = styled_status(s.get("status"))
                pane_ok = "[green]✓[/]" if s.get("pane_alive") else "[red]✗[/]"
                console.print(f"  {pane_ok} {name} [{status}]")

    _output(result, _fmt)


@session.command()
def cleanup() -> None:
    """Close all active sessions with dead tmux panes."""
    log = _cli_log()
    closed = _svc().cleanup()
    log.info("Cleanup complete", count=len(closed))

    def _fmt(data: dict) -> None:
        from cortex.cli.formatters import print_ok
        count = data.get("count", 0)
        if count == 0:
            click.echo("No dead sessions to clean up.")
        else:
            print_ok(f"Cleaned up {count} dead session(s)")
            for name in data.get("closed", []):
                click.echo(f"  - {name}")

    _output({"closed": closed, "count": len(closed)}, _fmt)


# ── Spatial ──────────────────────────────────────────────────


@session.command()
@click.argument("refs", nargs=-1, required=True)
@click.option("--layout", "layout_name", default="tiled", help="Layout: tiled, even-horizontal, etc.")
def gather(refs: tuple[str, ...], layout_name: str) -> None:
    """Gather sessions into a single window with a layout."""
    log = _cli_log()
    tmux = get_container().terminal

    panes: list[dict] = []
    for ref in refs:
        doc = _resolve_or_exit(ref)
        pane_id = doc.get("pane_id")
        if not pane_id or not tmux.pane_exists(pane_id):
            _error_exit(f"No live pane for '{doc.get('name', ref)}'")
        panes.append({"session_id": doc["_id"], "name": doc.get("name"), "pane_id": pane_id})

    if len(panes) < 2:
        _error_exit("Need at least 2 sessions to gather")

    target = panes[0]["pane_id"]
    moved = []
    for pane in panes[1:]:
        if tmux.join_pane(pane["pane_id"], target):
            moved.append(pane["name"])
        else:
            log.warning("join-pane failed", pane_id=pane["pane_id"])

    win_target = tmux.display_message(target, "#{session_name}:#{window_index}") or ""
    tmux.select_layout(win_target, layout_name)

    data = {"gathered": [p["name"] for p in panes], "layout": layout_name, "window": win_target}

    def _fmt(d: dict) -> None:
        from cortex.cli.formatters import print_ok
        names = ", ".join(d["gathered"])
        print_ok(f"Gathered {len(d['gathered'])} sessions: {names} (layout: {d['layout']})")

    _output(data, _fmt)


@session.command()
@click.argument("refs", nargs=-1, required=True)
def scatter(refs: tuple[str, ...]) -> None:
    """Break sessions into separate windows (tabs)."""
    log = _cli_log()
    tmux = get_container().terminal
    repo = _repo()

    scattered = []
    for ref in refs:
        doc = _resolve_or_exit(ref)
        pane_id = doc.get("pane_id")
        if not pane_id or not tmux.pane_exists(pane_id):
            log.warning("Skipping — no live pane", ref=ref)
            continue
        location = tmux.break_pane(pane_id)
        if location:
            new_pane_id = location.split(".")[-1] if "." in location else pane_id
            if new_pane_id != pane_id:
                repo.update(doc["_id"], {"pane_id": new_pane_id}, trigger="scatter", actor=_caller())
            scattered.append(doc.get("name"))

    data = {"scattered": scattered, "count": len(scattered)}

    def _fmt(d: dict) -> None:
        from cortex.cli.formatters import print_ok
        if d["count"] == 0:
            click.echo("No sessions scattered.")
        else:
            print_ok(f"Scattered {d['count']} session(s): {', '.join(d['scattered'])}")

    _output(data, _fmt)


@session.command()
@click.argument("ref")
@click.option("--beside", default=None, help="Move beside this session (horizontal)")
@click.option("--below", default=None, help="Move below this session (vertical)")
def move(ref: str, beside: str | None, below: str | None) -> None:
    """Move a session's pane beside or below another session."""
    tmux = get_container().terminal

    if not beside and not below:
        _error_exit("Specify --beside or --below target")

    doc = _resolve_or_exit(ref)
    pane_id = doc.get("pane_id")
    if not pane_id or not tmux.pane_exists(pane_id):
        _error_exit(f"No live pane for '{doc.get('name', ref)}'")

    target_ref = beside or below
    if target_ref.startswith("%"):
        target_pane = target_ref
    else:
        target_doc = _resolve_or_exit(target_ref)
        target_pane = target_doc.get("pane_id")
    if not target_pane or not tmux.pane_exists(target_pane):
        _error_exit(f"No live pane for target '{target_ref}'")

    orientation = "-h" if beside else "-v"
    if not tmux.move_pane(pane_id, target_pane, orientation):
        _error_exit("move-pane failed")

    data = {"moved": doc.get("name"), "beside" if beside else "below": target_ref}

    def _fmt(d: dict) -> None:
        from cortex.cli.formatters import print_ok
        direction = "beside" if beside else "below"
        print_ok(f"Moved {d['moved']} {direction} {target_ref}")

    _output(data, _fmt)


@session.command()
@click.option("--window", default=None, help="Filter to a specific window name or index")
def layout(window: str | None) -> None:
    """Show spatial layout of all panes with session mappings."""
    tmux = get_container().terminal
    repo = _repo()

    fmt = (
        "#{session_name}\t#{window_id}\t#{window_index}\t#{window_name}\t"
        "#{pane_id}\t#{pane_index}\t#{pane_left}\t#{pane_top}\t"
        "#{pane_width}\t#{pane_height}\t#{pane_active}\t#{pane_title}"
    )
    lines = tmux.list_panes_formatted(fmt)
    if not lines:
        _error_exit("tmux not running")

    sessions = repo.list({"status": {"$nin": ["completed", "closed"]}})
    pane_to_session: dict[str, str | None] = {}
    pane_to_color: dict[str, str | None] = {}
    for doc in sessions:
        pid = doc.get("pane_id")
        if pid:
            pane_to_session[str(pid)] = doc.get("name")
            pane_to_color[str(pid)] = doc.get("color")

    windows: dict[str, dict] = {}
    for line in lines:
        parts = line.split("\t")
        if len(parts) < 12:
            continue
        (sess_name, win_id, win_idx, win_name, pane_id, pane_idx,
         left, top, width, height, active, title) = parts[:12]

        if window is not None and win_name != window and win_idx != window:
            continue

        if win_id not in windows:
            windows[win_id] = {
                "id": win_id, "index": int(win_idx), "name": win_name,
                "workspace": sess_name, "panes": [],
            }

        windows[win_id]["panes"].append({
            "pane_id": pane_id, "session": pane_to_session.get(pane_id),
            "color": pane_to_color.get(pane_id),
            "left": int(left), "top": int(top),
            "width": int(width), "height": int(height),
            "index": int(pane_idx), "active": active == "1", "title": title,
        })

    workspace = "work"
    if windows:
        workspace = next(iter(windows.values())).get("workspace", "work")

    data = {"workspace": workspace, "windows": sorted(windows.values(), key=lambda w: w["index"])}

    def _fmt(d: dict) -> None:
        from cortex.cli.formatters import get_console, val
        console = get_console()
        console.print(f"[bold]Workspace:[/] {d['workspace']}")
        for win in d["windows"]:
            console.print(f"\n[bold]Window {win['index']}[/] — {win['name']}  [dim]({win['id']})[/]")
            for pane in win.get("panes", []):
                session_name = pane.get("session") or "[dim]—[/]"
                active = " [green]●[/]" if pane.get("active") else ""
                size = f"{pane.get('width', '?')}x{pane.get('height', '?')}"
                console.print(f"  {pane['pane_id']}  {session_name}{active}  [dim]{size}[/]")

    _output(data, _fmt)


# ── Paint ────────────────────────────────────────────────────


RUNTIME_BORDER_STYLES = {
    "working": "fg=#3fb950",
    "waiting_input": "fg=#d29922",
    "waiting_permission": "fg=#f85149",
    "error": "fg=#f85149",
    "unknown": "fg=#484f58",
}


@session.command()
@click.argument("ref", required=False)
@click.option("--color", default=None, help="Color name or #hex")
def paint(ref: str | None, color: str | None) -> None:
    """Set tmux pane border colors. Without args: paint all by runtime state."""
    tmux = get_container().terminal
    repo = _repo()
    named_colors = {
        "green": "#3fb950", "red": "#f85149", "amber": "#d29922",
        "blue": "#58a6ff", "purple": "#bc8cff", "gray": "#484f58",
    }

    if ref is not None:
        resolved = _resolve_or_exit(ref)
        pane_id = resolved.get("pane_id")
        if not pane_id or not tmux.pane_exists(pane_id):
            _error_exit(f"No live pane for session {ref}")
        style = named_colors.get(color, color) if color else RUNTIME_BORDER_STYLES.get(resolved.get("runtime", "unknown"), "fg=#484f58")
        if not style.startswith("fg="):
            style = f"fg={style}"
        tmux.set_pane_option(pane_id, "pane-border-style", style)
        _output(
            {"painted": [{"session_id": resolved["_id"], "pane_id": pane_id, "style": style}], "skipped": []},
            _fmt_paint_result,
        )
        return

    sessions = repo.list({"status": {"$nin": ["completed", "closed"]}})
    painted = []
    skipped = []
    for doc in sessions:
        pane_id = doc.get("pane_id")
        session_id = doc["_id"]
        if not pane_id or not tmux.pane_exists(pane_id):
            skipped.append({"session_id": session_id, "name": doc.get("name"), "reason": "no live pane"})
            continue
        if doc.get("color"):
            skipped.append({"session_id": session_id, "name": doc.get("name"), "reason": "has explicit color"})
            continue
        runtime = doc.get("runtime", "unknown")
        style = RUNTIME_BORDER_STYLES.get(runtime, "fg=#484f58")
        tmux.set_pane_option(pane_id, "pane-border-style", style)
        painted.append({"session_id": session_id, "pane_id": pane_id, "runtime": runtime, "style": style})

    _output({"painted": painted, "skipped": skipped}, _fmt_paint_result)


def _fmt_paint_result(data: dict) -> None:
    from cortex.cli.formatters import print_ok
    painted = data.get("painted", [])
    skipped = data.get("skipped", [])
    if painted:
        print_ok(f"Painted {len(painted)} pane(s)")
    if skipped:
        for s in skipped:
            click.echo(f"  [dim]skipped {s.get('name', '?')}: {s.get('reason', '?')}[/]")
    if not painted and not skipped:
        click.echo("Nothing to paint.")


# ── Watch ───────────────────────────────────────────────────


SESSION_COLOR_MAP = {
    "blue":    {"color": "#58a6ff", "bg": "#0d1a2d"},
    "green":   {"color": "#3fb950", "bg": "#0a1a0d"},
    "yellow":  {"color": "#d29922", "bg": "#1a1506"},
    "purple":  {"color": "#bc8cff", "bg": "#170d2e"},
    "orange":  {"color": "#d29922", "bg": "#1a1506"},
    "pink":    {"color": "#f778ba", "bg": "#1f0d18"},
    "cyan":    {"color": "#58a6ff", "bg": "#0d1a2d"},
    "red":     {"color": "#f85149", "bg": "#1f0a0a"},
}

FALLBACK_THEMES = [
    {"color": "#58a6ff", "bg": "#0d1a2d"},  # blue
    {"color": "#d29922", "bg": "#1a1506"},  # orange
    {"color": "#bc8cff", "bg": "#170d2e"},  # purple
    {"color": "#f85149", "bg": "#1f0a0a"},  # red
    {"color": "#3fb950", "bg": "#0a1a0d"},  # green
]


def _build_session_color_map() -> dict[str, dict[str, str]]:
    """Pre-populate color_map from active sessions in the registry."""
    repo = _repo()
    sessions = repo.list({"status": {"$nin": ["completed", "closed"]}}, brief=True)
    result: dict[str, dict[str, str]] = {}
    for doc in sessions:
        name = doc.get("name")
        cc_color = doc.get("color")
        if name and cc_color and cc_color in SESSION_COLOR_MAP:
            result[name] = SESSION_COLOR_MAP[cc_color]
    return result


def _get_sender_theme(sender: str, color_map: dict[str, dict[str, str]]) -> dict[str, str]:
    if sender not in color_map:
        used = len(color_map)
        color_map[sender] = FALLBACK_THEMES[used % len(FALLBACK_THEMES)]
    return color_map[sender]


def _lighten_hex(hex_color: str, amount: int = 20) -> str:
    """Lighten a hex color by adding to each RGB channel."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    r, g, b = min(r + amount, 255), min(g + amount, 255), min(b + amount, 255)
    return f"#{r:02x}{g:02x}{b:02x}"


def _render_message(console, msg, color_map: dict[str, dict[str, str]]) -> None:
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich.style import Style
    from rich.text import Text
    from rich.theme import Theme

    theme = _get_sender_theme(msg.sender, color_map)
    color = theme["color"]
    bg = theme["bg"]

    from datetime import datetime, timezone
    try:
        utc_dt = datetime.fromisoformat(msg.created_at).replace(tzinfo=timezone.utc)
        ts = utc_dt.astimezone().strftime("%H:%M:%S")
    except (ValueError, TypeError):
        ts = msg.created_at[11:19] if len(msg.created_at) >= 19 else msg.created_at
    meta = msg.meta or {}
    msg_type = meta.get("type", "")
    priority = meta.get("priority", "")

    badge_parts = []
    if msg_type:
        badge_parts.append(msg_type)
    if priority and priority != "normal":
        badge_parts.append(f"[bold red]{priority}[/]")
    badge = f" ({', '.join(badge_parts)})" if badge_parts else ""

    header = Text.from_markup(
        f"[bold {color}]{msg.sender}[/] [dim]→[/] [bold]{msg.recipient}[/]"
        f"  [dim]{ts}[/]{badge}"
    )

    content = msg.content.strip()
    try:
        body = Markdown(content)
    except Exception:
        body = Text(content)

    code_bg = _lighten_hex(bg, 20)
    code_theme = Theme({
        "markdown.code": f"bold bright_cyan on {code_bg}",
        "markdown.code_block": f"cyan on {code_bg}",
    })

    panel = Panel(
        body,
        title=header,
        title_align="left",
        border_style=Style(color=color),
        style=Style(bgcolor=bg),
        padding=(0, 1),
    )
    console.push_theme(code_theme)
    console.print(panel)
    console.pop_theme()


EVENT_ICONS = {
    "spawn": "+",
    "close": "x",
    "stale_sweep": "x",
    "health-check": "~",
}

EVENT_COLORS = {
    "active": "green",
    "completed": "dim",
    "closed": "red",
    "paused": "yellow",
    "blocked": "red",
    "idle": "yellow",
    "archived": "dim",
}


def _render_event(console, event: dict, color_map: dict[str, dict[str, str]]) -> None:
    from datetime import datetime, timezone

    ts_raw = event.get("at", "")
    try:
        utc_dt = datetime.fromisoformat(ts_raw).replace(tzinfo=timezone.utc)
        ts = utc_dt.astimezone().strftime("%H:%M:%S")
    except (ValueError, TypeError):
        ts = ts_raw[11:19] if len(ts_raw) >= 19 else ts_raw

    name = event.get("session_name", "?")
    to_status = event.get("to", "?")
    from_status = event.get("from")
    trigger = event.get("trigger", "")
    reason = event.get("reason")
    actor = event.get("actor")

    icon = EVENT_ICONS.get(trigger, "~")
    status_color = EVENT_COLORS.get(to_status, "white")

    if from_status:
        label = f"{name} {from_status} → [{status_color}]{to_status}[/]"
    else:
        label = f"{name} [{status_color}]{to_status}[/]"

    parts = []
    if actor:
        parts.append(f"[dim]by {actor}[/]")
    if reason:
        parts.append(f"[dim italic]{reason}[/]")
    suffix = "  " + "  ".join(parts) if parts else ""

    console.print(f"  [dim]{ts}[/]  {icon} {label}{suffix}")


def _strip_markdown(text: str) -> list[str]:
    """Strip markdown formatting to produce plain text for log-style display."""
    import re

    lines = text.strip().splitlines()
    cleaned = []
    in_code_block = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue
        if not stripped:
            continue
        # Strip header markers
        stripped = re.sub(r"^#{1,6}\s+", "", stripped)
        # Strip bold/italic markers
        stripped = stripped.replace("**", "").replace("__", "")
        # Strip bullet/list markers
        stripped = re.sub(r"^[-*+]\s+", "", stripped)
        stripped = re.sub(r"^\d+\.\s+", "", stripped)
        # Strip inline code backticks
        stripped = re.sub(r"`([^`]+)`", r"\1", stripped)
        # Strip markdown links [text](url) -> text
        stripped = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", stripped)
        stripped = stripped.strip()
        if stripped:
            cleaned.append(stripped)
    return cleaned


def _render_transcript(console, entry: dict, color_map: dict[str, dict[str, str]]) -> None:
    """Render a transcript entry as a single compact log line."""
    name = entry.get("session_name", "?")
    ts = entry.get("ts", "")
    text = entry.get("text", "")
    role = entry.get("role", "assistant")

    theme = _get_sender_theme(name, color_map)
    color = theme["color"]

    lines = _strip_markdown(text)
    if not lines:
        return

    from rich.markup import escape
    first_line = escape(lines[0])
    if len(first_line) > 120:
        first_line = first_line[:120] + "…"
    extra = f"  [dim](+{len(lines) - 1} lines)[/]" if len(lines) > 1 else ""

    if role == "user":
        console.print(f"  [dim]{ts}[/]  [bold {color}]{name}[/] [dim]⌨[/]  {first_line}{extra}")
    else:
        console.print(f"  [dim]{ts}[/]  [{color}]{name}[/] [dim]>[/]  [dim]{first_line}[/]{extra}")


class TranscriptTailer:
    """Tails transcript JSONL files for watched sessions."""

    def __init__(self, session_names: list[str] | None = None) -> None:
        self._names = session_names
        self._offsets: dict[str, int] = {}  # session_name -> file byte offset
        self._paths: dict[str, str] = {}    # session_name -> transcript_path
        self._poll_count = 0
        self._refresh_every = 5  # re-check registry every N polls

    def _resolve_paths(self) -> None:
        """Look up transcript_path from session registry for watched sessions."""
        repo = _repo()
        filters: dict = {"status": {"$nin": ["completed", "closed"]}}
        if self._names:
            filters["name"] = {"$in": self._names}
        sessions = repo.list(filters, brief=True)
        for doc in sessions:
            name = doc.get("name")
            path = doc.get("transcript_path")
            if name and path and name not in self._paths:
                self._paths[name] = path

    def poll(self) -> list[dict]:
        """Read new transcript entries since last poll. Returns timeline-compatible dicts."""
        self._poll_count += 1
        if not self._paths or self._poll_count % self._refresh_every == 0:
            self._resolve_paths()

        entries = []
        for name, path in list(self._paths.items()):
            try:
                entries.extend(self._read_new_lines(name, path))
            except (OSError, IOError):
                continue
        return entries

    def _read_new_lines(self, session_name: str, path: str) -> list[dict]:
        import os as _os

        try:
            file_size = _os.path.getsize(path)
        except OSError:
            return []

        offset = self._offsets.get(session_name, 0)
        if file_size <= offset:
            return []

        entries = []
        with open(path, "r") as f:
            f.seek(offset)
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                parsed = self._parse_entry(session_name, entry)
                if parsed:
                    entries.append(parsed)
            self._offsets[session_name] = f.tell()
        return entries

    @staticmethod
    def _parse_entry(session_name: str, entry: dict) -> dict | None:
        entry_type = entry.get("type", "")
        msg = entry.get("message", {})
        role = msg.get("role", "")

        if entry_type in ("assistant", "user") and role in ("assistant", "user"):
            text = _extract_text(msg.get("content", ""))
            if text:
                from datetime import datetime, timezone
                ts_raw = entry.get("timestamp", "")
                try:
                    if ts_raw:
                        utc_dt = datetime.fromisoformat(ts_raw).replace(tzinfo=timezone.utc)
                        ts = utc_dt.astimezone().strftime("%H:%M:%S")
                    else:
                        ts = datetime.now().strftime("%H:%M:%S")
                except (ValueError, TypeError):
                    ts = datetime.now().strftime("%H:%M:%S")
                return {
                    "kind": "transcript",
                    "session_name": session_name,
                    "role": role,
                    "text": text,
                    "ts": ts,
                    "sort_key": ts_raw or datetime.now(timezone.utc).isoformat(),
                }
        return None


def _extract_text(content) -> str:
    """Extract text from assistant message content (string or list of blocks)."""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        texts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                texts.append(block.get("text", ""))
        return "\n".join(texts).strip()
    return ""


def _merge_timeline(messages: list, events: list[dict], transcript: list[dict] | None = None) -> list:
    """Merge messages, events, and transcript entries into a single timeline sorted by timestamp."""
    timeline = []
    for m in messages:
        timeline.append(("msg", m.created_at, m))
    for e in events:
        timeline.append(("event", e.get("at", ""), e))
    if transcript:
        for t in transcript:
            timeline.append(("transcript", t.get("sort_key", ""), t))
    timeline.sort(key=lambda x: x[1])
    return timeline


WATCH_MODES = ("messages", "full", "interactive")


def _render_timeline_item(console, kind: str, item, color_map: dict[str, dict[str, str]], mode: str) -> None:
    if kind == "msg":
        _render_message(console, item, color_map)
    elif kind == "event":
        _render_event(console, item, color_map)
    elif kind == "transcript":
        role = item.get("role", "assistant")
        if mode == "interactive" and role != "user":
            return
        _render_transcript(console, item, color_map)


@session.command()
@click.argument("names", nargs=-1)
@click.option("--limit", "history_limit", default=50, help="Max initial messages (within last 24h)")
@click.option("--poll", "poll_interval", default=2.0, type=float, help="Poll interval in seconds")
@click.option("--no-live", is_flag=True, default=False, help="Show history and exit")
@click.option("--mode", "watch_mode", default="messages", type=click.Choice(WATCH_MODES),
              help="messages: channel messages only (default). full: messages + transcript. interactive: messages + user input.")
def watch(names: tuple[str, ...], history_limit: int, poll_interval: float, no_live: bool, watch_mode: str) -> None:
    """Live-tail messages between sessions in a chat view.

    \b
    Usage:
      cortex session watch name1 name2            # Messages between two sessions
      cortex session watch name1                   # All messages to/from one session
      cortex session watch                         # All inter-session messages
      cortex session watch name1 --mode full       # Messages + assistant transcript
      cortex session watch name1 --mode interactive # Messages + user input
    """
    import signal

    from rich.console import Console
    from rich.rule import Rule

    console = Console()
    container = get_container()
    msg_repo = container.messages
    session_repo = _repo()
    sessions = list(names) if names else None

    if sessions and len(sessions) > 2:
        _error_exit("At most 2 session names")

    include_transcript = watch_mode in ("full", "interactive")

    mode_label = f" [dim]({watch_mode})[/]" if watch_mode != "messages" else ""
    label = " & ".join(names) if names else "all sessions"
    console.print(Rule(f"[bold]Watching: {label}[/]{mode_label}"))

    color_map = _build_session_color_map()
    from datetime import datetime, timedelta, timezone
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    msgs = msg_repo.watch_messages(sessions=sessions, after=cutoff, limit=history_limit)
    events = session_repo.list_events(sessions=sessions, after=cutoff, limit=history_limit)

    # Transcript tailing (skip history on initial load — too noisy)
    tailer = TranscriptTailer(session_names=sessions) if include_transcript else None
    if tailer:
        # Seek to end of transcript files so we only show new entries
        tailer.poll()

    timeline = _merge_timeline(msgs, events)
    if not timeline:
        console.print("[dim]No history.[/]")
    else:
        for kind, _ts, item in timeline:
            _render_timeline_item(console, kind, item, color_map, watch_mode)

    if no_live:
        return

    last_ts = timeline[-1][1] if timeline else None
    console.print(Rule("[dim]live[/]"))

    def _on_resize(signum, frame):
        nonlocal console
        console = Console()

    signal.signal(signal.SIGWINCH, _on_resize)

    try:
        while True:
            time.sleep(poll_interval)
            new_msgs = msg_repo.watch_messages(sessions=sessions, after=last_ts)
            new_events = session_repo.list_events(sessions=sessions, after=last_ts)
            new_transcript = tailer.poll() if tailer else None
            for kind, ts, item in _merge_timeline(new_msgs, new_events, new_transcript):
                _render_timeline_item(console, kind, item, color_map, watch_mode)
                if kind != "transcript":
                    last_ts = ts
    except KeyboardInterrupt:
        console.print(Rule("[dim]stopped[/]"))
    finally:
        signal.signal(signal.SIGWINCH, signal.SIG_DFL)
