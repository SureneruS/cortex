from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from cortex import github
from cortex.config import load_config
from cortex.models import Checkpoint, Update
from cortex.state import StateManager

mcp = FastMCP("cortex", instructions="Cortex — persistent context brain for Claude Code sessions")

_state: StateManager | None = None


def _notify_dashboard() -> None:
    """Fire SSE notify on the dashboard HTTP server (separate process)."""
    import urllib.request

    try:
        req = urllib.request.Request("http://localhost:9400/api/dashboard/notify", method="POST")
        urllib.request.urlopen(req, timeout=1)
    except Exception:
        pass


def _get_state() -> StateManager:
    global _state
    if _state is None:
        config = load_config()
        _state = StateManager(config.resolved_db_path)
        _state.init_db()
        _state.on_mutation = _notify_dashboard
    return _state


@mcp.tool()
def cortex_get_active_streams(status: str | None = None) -> str:
    """List work streams. Defaults to active streams. Pass status='completed', 'paused', or 'all' to filter."""
    streams = _get_state().list_streams(status=status or "active")
    return json.dumps(
        [
            {
                "id": s.id,
                "title": s.title,
                "repos": s.repos,
                "status": s.status,
                "summary": s.summary,
                "metadata": s.metadata,
                "updated_at": s.updated_at.isoformat(),
            }
            for s in streams
        ],
        indent=2,
    )


@mcp.tool()
def cortex_get_context(topic: str) -> str:
    """Search history for a topic and return matching updates and decisions as raw records."""
    state = _get_state()
    results = state.search(topic)
    if not results:
        return json.dumps({"topic": topic, "results": []})
    items = []
    for r in results:
        if isinstance(r, Update):
            items.append(
                {
                    "type": "update",
                    "id": r.id,
                    "summary": r.summary,
                    "content": r.content,
                    "stream_id": r.stream_id,
                    "metadata": r.metadata,
                    "created_at": r.created_at.isoformat(),
                }
            )
        elif isinstance(r, Checkpoint):
            items.append(
                {
                    "type": "checkpoint",
                    "id": r.id,
                    "week_of": r.week_of,
                    "content": r.content,
                    "stream_ids": r.stream_ids,
                    "metadata": r.metadata,
                    "created_at": r.created_at.isoformat(),
                }
            )
        else:
            items.append(
                {
                    "type": "decision",
                    "id": r.id,
                    "what": r.what,
                    "why": r.why,
                    "stream_id": r.stream_id,
                    "metadata": r.metadata,
                    "created_at": r.created_at.isoformat(),
                }
            )
    return json.dumps({"topic": topic, "results": items}, indent=2)


@mcp.tool()
def cortex_get_stream_context(stream_id: str) -> str:
    """Get a stream's full history — all updates and decisions in chronological order."""
    ctx = _get_state().get_stream_context(stream_id)
    if not ctx:
        return json.dumps({"error": f"Stream {stream_id} not found"})
    return json.dumps(ctx, indent=2)


@mcp.tool()
def cortex_create_stream(title: str, repos: list[str], metadata: dict | None = None) -> str:
    """Create a new work stream for tracking a feature, task, or investigation. Optional metadata for tags, labels, etc."""
    stream = _get_state().create_stream(title, repos, metadata=metadata)
    return json.dumps(
        {"id": stream.id, "title": stream.title, "repos": stream.repos, "metadata": stream.metadata}
    )


@mcp.tool()
def cortex_update_stream(
    stream_id: str,
    title: str | None = None,
    status: str | None = None,
    repos: list[str] | None = None,
    summary: str | None = None,
    metadata: dict | None = None,
    replace_metadata: bool = False,
) -> str:
    """Update a stream's title, status, repos, summary, or metadata. By default metadata is merged with existing. Set replace_metadata=True to replace entirely."""
    try:
        stream = _get_state().update_stream(
            stream_id,
            title=title,
            status=status,
            repos=repos,
            summary=summary,
            metadata=metadata,
            merge_metadata=not replace_metadata,
        )
    except ValueError as e:
        return json.dumps({"error": str(e)})
    if not stream:
        return json.dumps({"error": f"Stream {stream_id} not found"})
    return json.dumps(
        {
            "id": stream.id,
            "title": stream.title,
            "status": stream.status,
            "repos": stream.repos,
            "metadata": stream.metadata,
        }
    )


@mcp.tool()
def cortex_delete_entry(entry_id: str, entry_type: str) -> str:
    """Delete an update, decision, or stream by ID. entry_type must be 'update', 'decision', or 'stream'. Deleting a stream cascades to all its updates and decisions."""
    state = _get_state()
    if entry_type == "update":
        state.delete_update(entry_id)
    elif entry_type == "decision":
        state.delete_decision(entry_id)
    elif entry_type == "stream":
        state.delete_stream(entry_id)
    else:
        return json.dumps(
            {
                "error": f"Unknown entry_type: {entry_type}. Must be 'update', 'decision', or 'stream'."
            }
        )
    return json.dumps({"deleted": entry_id, "type": entry_type})


@mcp.tool()
def cortex_edit_entry(
    entry_id: str,
    entry_type: str,
    content: str | None = None,
    summary: str | None = None,
    what: str | None = None,
    why: str | None = None,
    metadata: dict | None = None,
) -> str:
    """Edit an update or decision. For updates: pass content and/or summary. For decisions: pass what and/or why. Optional metadata replaces existing."""
    state = _get_state()
    if entry_type == "update":
        result = state.edit_update(entry_id, content=content, summary=summary, metadata=metadata)
        if not result:
            return json.dumps({"error": f"Update {entry_id} not found"})
        return json.dumps({"id": result.id, "summary": result.summary, "content": result.content})
    elif entry_type == "decision":
        result = state.edit_decision(entry_id, what=what, why=why, metadata=metadata)
        if not result:
            return json.dumps({"error": f"Decision {entry_id} not found"})
        return json.dumps({"id": result.id, "what": result.what, "why": result.why})
    else:
        return json.dumps(
            {"error": f"Unknown entry_type: {entry_type}. Must be 'update' or 'decision'."}
        )


@mcp.tool()
def cortex_link_session(session_id: str, stream_id: str, repo: str = "", branch: str = "") -> str:
    """Link a Claude Code session to a stream. Call this when starting work on a stream so tasks can be restored on session resume."""
    try:
        _get_state().link_session(session_id, stream_id, repo, branch)
    except ValueError as e:
        return json.dumps({"error": str(e)})
    return json.dumps({"linked": True, "session_id": session_id, "stream_id": stream_id})


@mcp.tool()
def cortex_log_update(
    stream_id: str, content: str, summary: str, metadata: dict | None = None
) -> str:
    """Log a progress update to a stream. Caller provides both full content and a short summary. Optional metadata for tags, session links, etc."""
    try:
        update = _get_state().add_update(stream_id, content, summary, metadata=metadata)
    except ValueError as e:
        return json.dumps({"error": str(e)})
    return json.dumps({"id": update.id, "summary": update.summary})


@mcp.tool()
def cortex_log_decision(stream_id: str, what: str, why: str, metadata: dict | None = None) -> str:
    """Log an architectural or design decision to a stream. Optional metadata for tags, ticket refs, etc."""
    try:
        decision = _get_state().add_decision(stream_id, what, why, metadata=metadata)
    except ValueError as e:
        return json.dumps({"error": str(e)})
    return json.dumps({"id": decision.id, "what": decision.what, "why": decision.why})


@mcp.tool()
def cortex_complete_stream(stream_id: str, summary: str) -> str:
    """Mark a stream as completed with a final summary."""
    _get_state().complete_stream(stream_id, summary)
    return json.dumps({"stream_id": stream_id, "status": "completed"})


@mcp.tool()
def cortex_search_history(query: str) -> str:
    """Search past updates and decisions. Uses semantic vector search (all-mpnet-base-v2) with FTS keyword fallback for exact terms and IDs."""
    results = _get_state().search(query)
    items = []
    for r in results:
        if isinstance(r, Update):
            items.append(
                {
                    "type": "update",
                    "id": r.id,
                    "summary": r.summary,
                    "content": r.content,
                    "stream_id": r.stream_id,
                    "metadata": r.metadata,
                    "created_at": r.created_at.isoformat(),
                }
            )
        elif isinstance(r, Checkpoint):
            items.append(
                {
                    "type": "checkpoint",
                    "id": r.id,
                    "week_of": r.week_of,
                    "content": r.content,
                    "stream_ids": r.stream_ids,
                    "metadata": r.metadata,
                    "created_at": r.created_at.isoformat(),
                }
            )
        else:
            items.append(
                {
                    "type": "decision",
                    "id": r.id,
                    "what": r.what,
                    "why": r.why,
                    "stream_id": r.stream_id,
                    "metadata": r.metadata,
                    "created_at": r.created_at.isoformat(),
                }
            )
    return json.dumps({"query": query, "results": items}, indent=2)


@mcp.tool()
def cortex_save_checkpoint(
    week_of: str,
    content: str,
    stream_ids: list[str] | None = None,
    metadata: dict | None = None,
) -> str:
    """Save a weekly checkpoint (upserts on week_of). week_of is the Monday ISO date (e.g. '2026-03-09'). If stream_ids omitted, auto-captures active streams."""
    checkpoint = _get_state().save_checkpoint(
        week_of, content, stream_ids=stream_ids, metadata=metadata
    )
    return json.dumps(
        {
            "id": checkpoint.id,
            "week_of": checkpoint.week_of,
            "stream_ids": checkpoint.stream_ids,
            "updated_at": checkpoint.updated_at.isoformat(),
        }
    )


@mcp.tool()
def cortex_get_checkpoint(week_of: str | None = None) -> str:
    """Get a weekly checkpoint. Returns latest if week_of is omitted, or specific week if provided (Monday ISO date)."""
    checkpoint = _get_state().get_checkpoint(week_of)
    if not checkpoint:
        return json.dumps({"error": "No checkpoint found"})
    return json.dumps(
        {
            "id": checkpoint.id,
            "week_of": checkpoint.week_of,
            "content": checkpoint.content,
            "stream_ids": checkpoint.stream_ids,
            "metadata": checkpoint.metadata,
            "created_at": checkpoint.created_at.isoformat(),
            "updated_at": checkpoint.updated_at.isoformat(),
        },
        indent=2,
    )


@mcp.tool()
def cortex_get_session_brief() -> str:
    """Quick status for hook injection. Returns compact summary of active streams + recent decisions (~500 tokens)."""
    state = _get_state()
    streams = state.get_active_streams()
    if not streams:
        return "No active Cortex streams."

    checkpoint = state.get_checkpoint()
    if checkpoint:
        lines = [f"Latest checkpoint (week of {checkpoint.week_of}):", checkpoint.content[:500], ""]
    else:
        lines = []
    lines.append("Active streams:")
    for s in streams:
        ctx = state.get_stream_context(s.id)
        recent_decisions = ctx["decisions"][-3:] if ctx["decisions"] else []
        recent_updates = ctx["updates"][-3:] if ctx["updates"] else []
        tag_str = ""
        if s.metadata and s.metadata.get("tags"):
            tag_str = f" ({', '.join(s.metadata['tags'])})"
        lines.append(f"\n## {s.title}{tag_str} [{', '.join(s.repos)}]")
        if s.summary:
            lines.append(f"  Summary: {s.summary}")
        for d in recent_decisions:
            lines.append(f"  Decision: {d['what']}")
        for u in recent_updates:
            lines.append(f"  Update: {u['summary']}")

    return "\n".join(lines)


@mcp.tool()
def cortex_post_dashboard(blueprint: dict) -> str:
    """Post a dashboard blueprint. Triggers watcher restart and SSE notification.

    Quick reference (call cortex_get_dashboard_schema for full spec):

    REQUIRED: schema_version (integer, currently 3). Fetch schema to get current version.
    Section types: metric-row, list, table, progress, changelog, text, chart, cortex-checkpoint, cortex-streams
    List variants: plain (default), checkbox (done: bool), badge (badge: {text, color})
    Table variants: default, compact
    Progress variants: bar (default), compact
    Badge colors: green, yellow, red, blue, purple, muted
    Metric colors: green, yellow, red, blue, muted
    Section props: title, size (sm|default), style (card|flat), variant, source (watcher),
      priority (high|normal|low), accent (red|yellow|blue|green|purple|muted),
      elevation (subtle|raised), font (mono|sans), density (compact|normal|spacious),
      barSize (sm|md|lg, progress only)
    Blueprint globals: density (compact|normal|spacious), font (mono|sans)
    List items: text, status, done, badge, badgePosition (inline|end), links[], cortex_stream,
      enrichment (tooltip|inline|block|hidden)
    Table cells: plain strings or {text, color, url} objects
    Links: {label (substring of text), url, type: pr|linear|notion|slack|figma|vscode|granola|url}
    Source (auto-refresh): {command, transform: passthrough|pr_table_rows|review_badge|ci_badge, interval: 60}
    Free-form styling: css (inline CSS object), className (Tailwind classes) on sections and items"""
    import urllib.request

    data = json.dumps(blueprint).encode()
    req = urllib.request.Request(
        "http://localhost:9400/api/dashboard/blueprint",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            return json.dumps({"id": result["id"], "status": "ok"})
    except urllib.request.HTTPError as e:
        body = e.read().decode()
        try:
            err = json.loads(body)
        except json.JSONDecodeError:
            err = {"detail": body}
        if e.code == 422:
            return json.dumps(
                {
                    "status": "schema_version_mismatch",
                    "error": err.get("detail", "Schema version mismatch"),
                    "current_version": err.get("current_version"),
                    "schema": err.get("schema"),
                }
            )
        return json.dumps({"status": "error", "error": err.get("detail", str(e))})
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)})


@mcp.tool()
def cortex_get_dashboard() -> str:
    """Get the current dashboard resolved data."""
    import urllib.request

    try:
        with urllib.request.urlopen(
            "http://localhost:9400/api/dashboard/resolved", timeout=5
        ) as resp:
            return resp.read().decode()
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)})


@mcp.tool()
def cortex_get_dashboard_schema() -> str:
    """Get the full dashboard blueprint JSON schema. Lists all section types, properties, variants, link types, and watcher config. Use this to discover available options when building or updating dashboards."""
    import urllib.request

    try:
        with urllib.request.urlopen(
            "http://localhost:9400/api/dashboard/schema", timeout=5
        ) as resp:
            return resp.read().decode()
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)})


_cron_mgr = None


def _get_cron():
    global _cron_mgr
    if _cron_mgr is None:
        from cortex.cron import CronManager
        from cortex.mongo import get_db

        _cron_mgr = CronManager(get_db())
    return _cron_mgr


@mcp.tool()
def cortex_cron_create(name: str, cron: str, action: str, action_args: dict | None = None) -> str:
    """Create a persistent cron job that runs on a schedule.
    Args:
        name: Unique job name
        cron: Standard 5-field cron expression (e.g. "*/5 * * * *" for every 5 min)
        action: Action type — "check-watches" or "command"
        action_args: Action-specific args (e.g. {"command": "echo hello"} for command type)
    """
    try:
        job = _get_cron().create(name, cron, action, action_args)
    except ValueError as e:
        return json.dumps({"error": str(e)})
    return json.dumps(job, indent=2, default=str)


@mcp.tool()
def cortex_cron_list() -> str:
    """List all persistent cron jobs with their status and schedule."""
    jobs = _get_cron().list()
    return json.dumps(jobs, indent=2, default=str)


@mcp.tool()
def cortex_cron_delete(name: str) -> str:
    """Delete a cron job by name.
    Args:
        name: The job name to delete
    """
    try:
        _get_cron().delete(name)
    except ValueError as e:
        return json.dumps({"error": str(e)})
    return json.dumps({"deleted": name})


@mcp.tool()
def cortex_cron_pause(name: str) -> str:
    """Pause a cron job (stops execution but keeps the job).
    Args:
        name: The job name to pause
    """
    try:
        job = _get_cron().pause(name)
    except ValueError as e:
        return json.dumps({"error": str(e)})
    return json.dumps(job, indent=2, default=str)


@mcp.tool()
def cortex_cron_resume(name: str) -> str:
    """Resume a paused cron job.
    Args:
        name: The job name to resume
    """
    try:
        job = _get_cron().resume(name)
    except ValueError as e:
        return json.dumps({"error": str(e)})
    return json.dumps(job, indent=2, default=str)


@mcp.tool()
def cortex_daemon_start() -> str:
    """Start the Cortex background daemon for cron job execution."""
    return _run_cli("daemon", "start")


@mcp.tool()
def cortex_daemon_stop() -> str:
    """Stop the Cortex background daemon."""
    return _run_cli("daemon", "stop")


@mcp.tool()
def cortex_daemon_status() -> str:
    """Check if the Cortex daemon is running."""
    return _run_cli("daemon", "status")


_log_dir = Path.home() / ".cortex" / "logs"
_log_dir.mkdir(parents=True, exist_ok=True)

_session_log = logging.getLogger("cortex.session.mcp")
_session_log.setLevel(logging.DEBUG)
if not _session_log.handlers:
    _h = logging.StreamHandler(sys.stderr)
    _h.setFormatter(
        logging.Formatter("[%(asctime)s] %(name)s %(levelname)s: %(message)s", datefmt="%H:%M:%S")
    )
    _session_log.addHandler(_h)
    _fh = logging.FileHandler(_log_dir / "session.log")
    _fh.setFormatter(
        logging.Formatter(
            "[%(asctime)s] %(name)s %(levelname)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
        )
    )
    _session_log.addHandler(_fh)


def _run_cli(*args: str) -> str:
    import subprocess

    cmd = ["cortex", *args]
    _session_log.info("CLI call: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    _session_log.info("CLI exit code: %d", result.returncode)
    if result.stdout:
        _session_log.debug("CLI stdout: %s", result.stdout[:500])
    if result.stderr:
        _session_log.warning("CLI stderr: %s", result.stderr[:500])
    if result.returncode != 0:
        error = result.stderr or result.stdout or f"CLI exited with code {result.returncode}"
        _session_log.error("CLI failed: %s", error[:500])
        return json.dumps({"ok": False, "error": error.strip()})
    return result.stdout


@mcp.tool()
def cortex_session_spawn(
    name: str, goal: str | None = None, workspace: str = "default", model: str | None = None
) -> str:
    """Spawn a new Claude Code session in a tmux pane and register it in the session registry.

    Use this when the user asks to create, spawn, or start a session — NOT the Agent tool or subagents.

    Args:
        name: Human-readable session name (e.g. "fix-login-bug")
        goal: What the session should accomplish
        workspace: "default" opens in current tmux session (configurable via CORTEX_SPAWN_MODE env: tab/split/window), "background" opens in a detached background tmux session
        model: Claude model alias (e.g. "haiku", "sonnet", "opus") or full model ID. Default: inherits from environment.

    Returns JSON with session_id, pane_id, name, workspace, goal.
    The spawned session gets CORTEX_SESSION_ROLE=worker and a system prompt."""
    _session_log.info(
        "MCP cortex_session_spawn called: name=%s goal=%s workspace=%s model=%s",
        name,
        goal,
        workspace,
        model,
    )
    args = ["session", "spawn", "--name", name, "--workspace", workspace]
    if goal:
        args.extend(["--goal", goal])
    if model:
        args.extend(["--model", model])
    result = _run_cli(*args)
    _session_log.info("MCP cortex_session_spawn result: %s", result[:200] if result else "empty")
    return result


@mcp.tool()
def cortex_session_list(status: str | None = None) -> str:
    """List all sessions in the Cortex session registry.

    Use this when the user asks to list, show, or check sessions — NOT Claude Code's built-in session list.

    Args:
        status: Filter by lifecycle status — "active", "idle", "paused", "blocked", "watching", "completed", "dead", or None for all.

    Returns JSON array of session documents with fields: _id, name, goal, status, runtime, pane_id, workspace, role, spawned_by, created_at, events. Sessions with status='watching' have a 'watch' field with PR/trigger details (set via cortex_pr_watch)."""
    _session_log.info("MCP cortex_session_list called: status=%s", status)
    args = ["session", "list"]
    if status:
        args.extend(["--status", status])
    result = _run_cli(*args)
    _session_log.info("MCP cortex_session_list returned %d chars", len(result) if result else 0)
    return result


@mcp.tool()
def cortex_session_get(session_id: str) -> str:
    """Get full details of a Cortex session by its registry ID.

    Returns the complete session document including name, goal, status, pane_id, workspace, role, spawned_by, created_at, and any custom fields."""
    _session_log.info("MCP cortex_session_get called: session_id=%s", session_id)
    result = _run_cli("session", "get", session_id)
    _session_log.info("MCP cortex_session_get result: %s", result[:200] if result else "empty")
    return result


@mcp.tool()
def cortex_session_update(session_id: str, data: dict) -> str:
    """Update a Cortex session's fields. Merges the provided fields into the existing session document.

    Status and runtime changes are validated and recorded as events in the session's event log.
    Valid status values: active, idle, paused, blocked, watching, completed, dead.
    Valid runtime values: working, waiting_input, waiting_permission, error, unknown.

    Args:
        session_id: The session registry ID to update.
        data: Dictionary of fields to merge (e.g. {"status": "paused", "runtime": "waiting_input"}).

    Returns the updated session document as JSON."""
    import json as _json

    _session_log.info("MCP cortex_session_update called: session_id=%s data=%s", session_id, data)
    result = _run_cli("session", "update", session_id, "--data", _json.dumps(data))
    _session_log.info("MCP cortex_session_update result: %s", result[:200] if result else "empty")
    return result


@mcp.tool()
def cortex_session_send(session_id: str, text: str) -> str:
    """Send text to a running session's terminal pane (and press Enter).

    Use this to send instructions, commands, or messages to a worker session.

    Args:
        session_id: The session registry ID.
        text: The text to send (will be followed by Enter).

    Returns JSON with ok, session_id, pane_id."""
    _session_log.info(
        "MCP cortex_session_send called: session_id=%s text=%r", session_id, text[:100]
    )
    result = _run_cli("session", "send", session_id, text)
    _session_log.info("MCP cortex_session_send result: %s", result[:200] if result else "empty")
    return result


@mcp.tool()
def cortex_session_capture(session_id: str, lines: int = 50) -> str:
    """Capture terminal output from a running session's tmux pane.

    Use this to read what a worker session is currently showing — check progress,
    read errors, see if it's idle, or monitor output.

    Args:
        session_id: The session registry ID.
        lines: Number of scrollback lines to capture (default 50).

    Returns JSON with session_id, pane_id, and output (the terminal text)."""
    _session_log.info(
        "MCP cortex_session_capture called: session_id=%s lines=%d", session_id, lines
    )
    result = _run_cli("session", "capture", session_id, "--lines", str(lines))
    _session_log.info("MCP cortex_session_capture result: %d chars", len(result) if result else 0)
    return result


@mcp.tool()
def cortex_session_close(session_id: str, force: bool = False) -> str:
    """Close a Cortex session with full wrapup lifecycle.

    Lifecycle: send /memorize to worker pane, wait for completion, update linked Cortex stream,
    close registry entry (status=completed, closed_at), kill tmux pane.

    Args:
        session_id: The session registry ID to close.
        force: Skip /memorize and close immediately (default False).

    Returns the closed session document as JSON."""
    _session_log.info("MCP cortex_session_close called: session_id=%s force=%s", session_id, force)
    args = ["session", "close", session_id]
    if force:
        args.append("--force")
    result = _run_cli(*args)
    _session_log.info("MCP cortex_session_close result: %s", result[:200] if result else "empty")
    return result


@mcp.tool()
def cortex_session_health() -> str:
    """Check health of all non-terminal sessions — detect dead panes, persist runtime state.

    Persists runtime observations (working/waiting_input) and marks dead panes (status=dead).
    All state changes are recorded as events in each session's event log.

    Returns JSON array with fields: session_id, name, pane_id, status, runtime, pane_status."""
    _session_log.info("MCP cortex_session_health called")
    result = _run_cli("session", "health")
    _session_log.info("MCP cortex_session_health returned %d chars", len(result) if result else 0)
    return result


@mcp.tool()
def cortex_session_cleanup() -> str:
    """Close all non-terminal sessions that have dead tmux panes.

    Finds sessions not yet completed/dead whose tmux pane no longer exists,
    and closes them (status=completed, trigger=cleanup). Returns count and list of closed sessions."""
    _session_log.info("MCP cortex_session_cleanup called")
    result = _run_cli("session", "cleanup")
    _session_log.info("MCP cortex_session_cleanup result: %s", result[:200] if result else "empty")
    return result


@mcp.tool()
def cortex_pr_state(number: int, repo: str | None = None) -> str:
    """Get PR state summary: state, reviewDecision, CI checks, comment/review counts.
    Returns JSON matching the watch last_state format.
    Args:
        number: PR number
        repo: Repository in owner/repo format (auto-detected from git if omitted)
    """
    try:
        result = github.pr_state(number, repo=repo)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def cortex_pr_threads(number: int, repo: str | None = None) -> str:
    """List all review threads on a PR with thread IDs, resolved status, author, body, file.
    Args:
        number: PR number
        repo: Repository in owner/repo format (auto-detected from git if omitted)
    """
    try:
        result = github.pr_threads(number, repo=repo)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def cortex_pr_checks(number: int, repo: str | None = None) -> str:
    """Get CI check details for a PR: check name, status, conclusion.
    Args:
        number: PR number
        repo: Repository in owner/repo format (auto-detected from git if omitted)
    """
    try:
        result = github.pr_checks(number, repo=repo)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def cortex_pr_react(number: int, comment_id: int, reaction: str, repo: str | None = None) -> str:
    """React to a PR review comment with thumbs up or down.
    Args:
        number: PR number
        comment_id: The comment's database ID
        reaction: "+1" for thumbs up, "-1" for thumbs down
        repo: Repository in owner/repo format (auto-detected from git if omitted)
    """
    try:
        github.pr_react(number, comment_id, reaction, repo=repo)
        return json.dumps({"ok": True, "reaction": reaction, "comment_id": comment_id})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def cortex_pr_resolve(thread_id: str) -> str:
    """Resolve a PR review thread.
    Args:
        thread_id: The GraphQL thread ID (starts with PRRT_)
    """
    try:
        github.pr_resolve(thread_id)
        return json.dumps({"ok": True, "thread_id": thread_id, "resolved": True})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def cortex_pr_batch_resolve(items: list[dict], repo: str | None = None) -> str:
    """React to and resolve multiple PR review threads in one call.
    Args:
        items: List of dicts with keys: comment_id (int), thread_id (str), reaction (str: "+1" or "-1")
        repo: Repository in owner/repo format (auto-detected from git if omitted)
    Each item gets a reaction on the comment and the thread gets resolved.
    """
    results = []
    for item in items:
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
    return json.dumps(results, indent=2)


@mcp.tool()
def cortex_pr_reply(number: int, comment_id: int, body: str, repo: str | None = None) -> str:
    """Reply to a PR review comment.
    Args:
        number: PR number
        comment_id: The comment's database ID
        body: Reply text
        repo: Repository in owner/repo format (auto-detected from git if omitted)
    """
    try:
        github.pr_reply(number, comment_id, body, repo=repo)
        return json.dumps({"ok": True, "comment_id": comment_id})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def cortex_pr_watch(number: int, session_id: str, repo: str | None = None, message: str | None = None) -> str:
    """Register a session to watch a PR for changes. Sets session status to 'watching' and stores watch config (type, repo, number, last_state) in the session document. Use session_list(status='watching') to see all watched sessions.
    Args:
        number: PR number
        session_id: Cortex session ID to register for watching
        repo: Repository in owner/repo format (auto-detected from git if omitted)
        message: Custom message to send when changes are detected (skips haiku composition). Use this to tell the session what to do, e.g. "Dependent PR merged. Rebase on origin/main and create a PR."
    """
    _session_log.info("PR watch registration: session=%s pr=%s#%s", session_id, repo, number)
    try:
        state = github.pr_state(number, repo=repo)
        watch_config: dict = {
            "type": "pr",
            "repo": repo,
            "number": number,
            "last_state": state,
        }
        if message:
            watch_config["message"] = message
        watch_data = {
            "status": "watching",
            "watch": watch_config,
        }
        _run_cli("session", "update", session_id, "--data", json.dumps(watch_data))
        _session_log.info(
            "PR watch registered: session=%s pr=%s#%s ci_checks=%d reviews=%d",
            session_id,
            repo,
            number,
            len(state.get("ciChecks", {})),
            state.get("reviewCount", 0),
        )
        return json.dumps({"ok": True, "session_id": session_id, "pr": number, "baseline": state})
    except Exception as e:
        _session_log.error("PR watch registration failed: session=%s error=%s", session_id, e)
        return json.dumps({"error": str(e)})


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
