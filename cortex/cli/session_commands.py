from __future__ import annotations

import json
import time
from pathlib import Path

import click

from cortex.cli import _cli_log, _error_exit, _json_out, get_container
from cortex.services.session_service import ClosePermissionDenied, SessionNotFound, SpawnDenied


@click.group()
def session() -> None:
    """Manage Claude Code sessions."""
    pass


def _svc():
    return get_container().session_service


def _repo():
    return get_container().sessions


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
        import os
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

    _json_out(result)


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


@session.command("list")
@click.option("--status", "filter_status", default=None, help="Filter by status")
@click.option("--runtime", "filter_runtime", default=None, help="Filter by runtime state")
@click.option("--brief", is_flag=True, default=False, help="Omit events and watch details")
@click.option("--limit", "limit", type=int, default=None, help="Max sessions to return")
def list_sessions(
    filter_status: str | None,
    filter_runtime: str | None,
    brief: bool,
    limit: int | None,
) -> None:
    """List registered sessions. Shows active sessions by default."""
    repo = _repo()
    filters = {}
    if filter_status and filter_status != "all":
        filters["status"] = filter_status
    elif not filter_status:
        filters["status"] = {"$nin": ["completed", "dead"]}
    if filter_runtime:
        filters["runtime"] = filter_runtime
    sessions = repo.list(filters, brief=brief, limit=limit)
    _json_out(sessions)


@session.command()
@click.argument("session_id")
def get(session_id: str) -> None:
    """Get a session by ID, name, or ID prefix."""
    doc = _resolve_or_exit(session_id)
    _json_out(doc)


@session.command()
@click.argument("ref")
@click.option("--all", "include_dead", is_flag=True, help="Include completed/dead children")
def children(ref: str, include_dead: bool) -> None:
    """List direct child sessions spawned by a session."""
    try:
        result = _svc().children(ref, include_dead=include_dead)
    except (SessionNotFound, ValueError) as e:
        _error_exit(str(e))
    _json_out(result)


@session.command()
@click.argument("ref", required=False)
def tree(ref: str | None) -> None:
    """Show session hierarchy as a tree."""
    try:
        result = _svc().tree(ref)
    except (SessionNotFound, ValueError) as e:
        _error_exit(str(e))
    _json_out(result)


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
    _json_out(doc)


@session.command()
@click.argument("session_id")
@click.option("--data", required=True, help="JSON object of fields to merge")
@click.option("--trigger", default="update", help="What triggered this update")
def update(session_id: str, data: str, trigger: str) -> None:
    """Update a session's fields."""
    log = _cli_log()
    try:
        fields = json.loads(data)
    except json.JSONDecodeError as e:
        _error_exit(f"Invalid JSON: {e}")
    doc = _resolve_or_exit(session_id)
    try:
        result = _repo().update(doc["_id"], fields, trigger=trigger)
    except ValueError as e:
        _error_exit(str(e))
    log.info("Session updated", session_id=doc["_id"])
    _json_out(result)


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
    _json_out(result)


# ── Message ──────────────────────────────────────────────────


@session.command()
@click.argument("session_name")
@click.argument("content")
@click.option("--thread-id", default=None, help="Thread ID for conversation linking")
def message(session_name: str, content: str, thread_id: str | None) -> None:
    """Send a message to a session via channels."""
    try:
        result = _svc().send_message(session_name, content, thread_id=thread_id)
    except SessionNotFound as e:
        _error_exit(str(e))
    _json_out(result)


@session.command()
@click.argument("session_name", required=False, default=None)
@click.option("--to", "to_filter", default=None, help="Filter by recipient")
@click.option("--limit", "limit_count", type=int, default=20, help="Max messages")
def messages(session_name: str | None, to_filter: str | None, limit_count: int) -> None:
    """View recent inter-session messages."""
    msgs = get_container().messages.list_messages(
        session_name=session_name, to_filter=to_filter, limit=limit_count
    )
    if not msgs:
        click.echo("No messages found.")
        return
    for m in reversed(msgs):
        ts = m.created_at[:19] if m.created_at else "?"
        msg_type = m.meta.get("type", "?") if m.meta else "?"
        content_preview = m.content[:120]
        click.echo(f"  [{ts}] {m.sender} -> {m.recipient} ({msg_type}, {m.status}): {content_preview}")


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
    _json_out(result)


@session.command()
@click.argument("session_id")
@click.option("--force", is_flag=True, help="Skip wrapup and close immediately")
@click.option("--cascade", is_flag=True, help="Also close all descendant sessions")
def close(session_id: str, force: bool, cascade: bool) -> None:
    """Close a session with channels-first wrapup."""
    log = _cli_log()
    log.info("CLI session close called", session_id=session_id, force=force, cascade=cascade)
    try:
        doc = _svc().close(session_id, force=force, cascade=cascade)
    except (SessionNotFound, ValueError, ClosePermissionDenied) as e:
        _error_exit(str(e))
    _json_out(doc)


@session.command("auto-close")
@click.argument("pane_id")
def auto_close(pane_id: str) -> None:
    """Close a session by its tmux pane_id (used by tmux hooks)."""
    log = _cli_log()
    log.info("CLI auto-close called", pane_id=pane_id)
    repo = _repo()
    sessions = repo.list({"status": {"$nin": ["completed", "dead"]}, "pane_id": pane_id})
    if not sessions:
        _error_exit(f"No active session for pane {pane_id}")
    doc = sessions[0]
    result = repo.close(doc["_id"], trigger="auto-close")
    log.info("Auto-closed session", session_id=doc["_id"])
    _json_out(result)


@session.command()
@click.argument("session_id")
def pause(session_id: str) -> None:
    """Pause a session — sends /exit, preserves cc_session_id for resume."""
    try:
        doc = _svc().pause(session_id)
    except (SessionNotFound, ValueError) as e:
        _error_exit(str(e))
    _json_out(doc)


@session.command()
@click.argument("session_id")
def resume(session_id: str) -> None:
    """Resume a paused session."""
    try:
        doc = _svc().resume(session_id)
    except (SessionNotFound, ValueError) as e:
        _error_exit(str(e))
    _json_out(doc)


@session.command()
@click.argument("session_id")
def hide(session_id: str) -> None:
    """Move a session to the background workspace."""
    try:
        doc = _svc().hide(session_id)
    except (SessionNotFound, ValueError, RuntimeError) as e:
        _error_exit(str(e))
    _json_out(doc)


@session.command()
@click.argument("session_id")
def show(session_id: str) -> None:
    """Bring a hidden session back from background."""
    try:
        doc = _svc().show(session_id)
    except (SessionNotFound, ValueError, RuntimeError) as e:
        _error_exit(str(e))
    _json_out(doc)


@session.command()
@click.argument("session_id")
def restart(session_id: str) -> None:
    """Restart CC — pause then resume with new CC version."""
    import subprocess

    log = _cli_log()
    result = subprocess.run(
        ["cortex", "session", "pause", session_id],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        _error_exit(f"Pause failed: {result.stdout}")

    result = subprocess.run(
        ["cortex", "session", "resume", session_id],
        capture_output=True, text=True, timeout=15,
    )
    if result.returncode != 0:
        _error_exit(f"Resume failed: {result.stdout}")

    doc = json.loads(result.stdout)
    log.info("Session restarted", session_id=session_id)
    _json_out(doc)


# ── Health / Cleanup ─────────────────────────────────────────


@session.command()
def health() -> None:
    """Comprehensive health check."""
    result = _svc().health_check()
    _json_out(result)


@session.command()
def cleanup() -> None:
    """Close all active sessions with dead tmux panes."""
    log = _cli_log()
    closed = _svc().cleanup()
    log.info("Cleanup complete", count=len(closed))
    _json_out({"closed": closed, "count": len(closed)})


# ── Spatial ──────────────────────────────────────────────────


@session.command()
@click.argument("refs", nargs=-1, required=True)
@click.option("--layout", "layout_name", default="tiled", help="Layout: tiled, even-horizontal, etc.")
def gather(refs: tuple[str, ...], layout_name: str) -> None:
    """Gather sessions into a single window with a layout."""
    log = _cli_log()
    svc = _svc()
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

    _json_out({"gathered": [p["name"] for p in panes], "layout": layout_name, "window": win_target})


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
                repo.update(doc["_id"], {"pane_id": new_pane_id}, trigger="scatter")
            scattered.append(doc.get("name"))

    _json_out({"scattered": scattered, "count": len(scattered)})


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

    _json_out({"moved": doc.get("name"), "beside" if beside else "below": target_ref})


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

    sessions = repo.list({"status": {"$nin": ["completed", "dead"]}})
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

    _json_out({"workspace": workspace, "windows": sorted(windows.values(), key=lambda w: w["index"])})


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
        _json_out({"painted": [{"session_id": resolved["_id"], "pane_id": pane_id, "style": style}], "skipped": []})
        return

    sessions = repo.list({"status": {"$nin": ["completed", "dead"]}})
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

    _json_out({"painted": painted, "skipped": skipped})


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
    sessions = repo.list({"status": {"$nin": ["completed", "dead"]}}, brief=True)
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


def _render_message(console, msg, color_map: dict[str, dict[str, str]]) -> None:
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich.style import Style
    from rich.text import Text

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

    panel = Panel(
        body,
        title=header,
        title_align="left",
        border_style=Style(color=color),
        style=Style(bgcolor=bg),
        padding=(0, 1),
    )
    console.print(panel)


@session.command()
@click.argument("names", nargs=-1)
@click.option("--limit", "history_limit", default=50, help="Max initial messages (within last 24h)")
@click.option("--poll", "poll_interval", default=2.0, type=float, help="Poll interval in seconds")
@click.option("--no-live", is_flag=True, default=False, help="Show history and exit")
def watch(names: tuple[str, ...], history_limit: int, poll_interval: float, no_live: bool) -> None:
    """Live-tail messages between sessions in a chat view.

    \b
    Usage:
      cortex session watch name1 name2   # Messages between two sessions
      cortex session watch name1          # All messages to/from one session
      cortex session watch                # All inter-session messages
    """
    import signal

    from rich.console import Console
    from rich.rule import Rule
    from rich.theme import Theme

    watch_theme = Theme({
        "markdown.code": "bold bright_cyan",
        "markdown.code_block": "cyan",
    })
    console = Console(theme=watch_theme)
    repo = get_container().messages
    sessions = list(names) if names else None

    if sessions and len(sessions) > 2:
        _error_exit("At most 2 session names")

    label = " & ".join(names) if names else "all sessions"
    console.print(Rule(f"[bold]Watching: {label}[/]"))

    color_map = _build_session_color_map()
    from datetime import datetime, timedelta, timezone
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    msgs = repo.watch_messages(sessions=sessions, after=cutoff, limit=history_limit)

    if not msgs:
        console.print("[dim]No message history.[/]")
    else:
        for m in msgs:
            _render_message(console, m, color_map)

    if no_live:
        return

    last_ts = msgs[-1].created_at if msgs else None
    console.print(Rule("[dim]live[/]"))

    def _on_resize(signum, frame):
        nonlocal console
        console = Console(theme=watch_theme)

    signal.signal(signal.SIGWINCH, _on_resize)

    try:
        while True:
            time.sleep(poll_interval)
            new_msgs = repo.watch_messages(sessions=sessions, after=last_ts)
            for m in new_msgs:
                _render_message(console, m, color_map)
                last_ts = m.created_at
    except KeyboardInterrupt:
        console.print(Rule("[dim]stopped[/]"))
    finally:
        signal.signal(signal.SIGWINCH, signal.SIG_DFL)
