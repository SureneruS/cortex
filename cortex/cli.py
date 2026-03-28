from __future__ import annotations

import click

from cortex.config import CONFIG_PATH, CORTEX_DIR, load_config, save_config, Config
from cortex.mongo import get_db
from cortex.mongo_state import MongoStateManager


@click.group()
def cli() -> None:
    """Cortex — persistent context brain for Claude Code."""
    from cortex.observability import bind_correlation, setup_logging

    setup_logging("cli")
    bind_correlation()


@cli.command()
def init() -> None:
    """Initialize Cortex: create config, DB, and scan repos for context."""
    click.echo("Initializing Cortex...")

    if CONFIG_PATH.exists():
        config = load_config()
        click.echo(f"  Config already exists at {CONFIG_PATH}")
    else:
        config = Config()
        save_config(config)
        click.echo(f"  Config saved to {CONFIG_PATH}")

    state = MongoStateManager(get_db(), config.resolved_vec_db_path)
    state.init_db()
    click.echo("  Database initialized (MongoDB + vec index)")

    click.echo("  Scanning repos for open PRs...")
    from cortex.bootstrap import scan_repos

    stats = scan_repos(config, state)

    click.echo("\nBootstrap complete:")
    click.echo(f"  Repos scanned: {stats['repos_scanned']}")
    click.echo(f"  Open PRs found: {stats['prs_found']}")
    click.echo(f"  Active branches: {stats['branches_found']}")
    click.echo(f"  Streams created: {stats['streams_created']}")
    if stats["streams_skipped"]:
        click.echo(f"  Streams skipped (already exist): {stats['streams_skipped']}")

    state.close()

    _install_fish_completions()


def _install_fish_completions() -> None:
    """Symlink fish completions from the cortex repo."""
    import os
    from pathlib import Path

    src = Path(__file__).resolve().parent.parent / "plugin" / "host" / "fish" / "cortex.fish"
    dest = Path.home() / ".config" / "fish" / "completions" / "cortex.fish"

    if not src.exists():
        return

    dest.parent.mkdir(parents=True, exist_ok=True)

    if dest.is_symlink() or dest.exists():
        os.remove(dest)

    os.symlink(src, dest)
    click.echo(f"  Fish completions: {dest} → {src}")


@cli.command()
def status() -> None:
    """Show active Cortex streams."""
    config = load_config()
    state = MongoStateManager(get_db(), config.resolved_vec_db_path)
    state.init_db()
    streams = state.get_active_streams()

    if not streams:
        click.echo("No active streams.")
        return

    for s in streams:
        click.echo(f"  [{s.id}] {s.title}  ({', '.join(s.repos)})")
        if s.summary:
            click.echo(f"          {s.summary}")

    state.close()


@cli.command()
def brief() -> None:
    """Print compact session brief (for hook injection)."""
    config = load_config()
    state = MongoStateManager(get_db(), config.resolved_vec_db_path)
    state.init_db()
    streams = state.get_active_streams()

    if not streams:
        return

    lines = ["[Cortex] Active streams:"]
    for s in streams[:5]:
        ctx = state.get_stream_context(s.id)
        recent_decisions = ctx["decisions"][-3:] if ctx["decisions"] else []
        recent_updates = ctx["updates"][-2:] if ctx["updates"] else []
        lines.append(f"  • {s.title} [{', '.join(s.repos)}]")
        for d in recent_decisions:
            lines.append(f"    Decision: {d['what']}")
        for u in recent_updates:
            lines.append(f"    Update: {u['summary']}")

    click.echo("\n".join(lines))
    state.close()


@cli.command()
@click.argument("session_id")
@click.argument("stream_id")
def link(session_id: str, stream_id: str) -> None:
    """Link a session to a stream."""
    config = load_config()
    state = MongoStateManager(get_db(), config.resolved_vec_db_path)
    state.init_db()
    state.link_session(session_id, stream_id)
    state.close()


@cli.command()
@click.option("--session-id", default=None, help="Claude Code session ID to restore tasks for.")
def tasks(session_id: str | None) -> None:
    """Print pending task backups for session restore."""
    config = load_config()
    state = MongoStateManager(get_db(), config.resolved_vec_db_path)
    state.init_db()

    if session_id:
        stream_ids = state.get_streams_for_session(session_id)
    else:
        stream_ids = [s.id for s in state.get_active_streams()]

    if not stream_ids:
        state.close()
        return

    for sid in stream_ids:
        ctx = state.get_stream_context(sid)
        if not ctx:
            continue
        for u in reversed(ctx["updates"]):
            meta = u.get("metadata") or {}
            if meta.get("type") == "task_backup":
                click.echo(
                    f"[Cortex] Pending tasks from last session (stream: {ctx['stream']['title']}):"
                )
                click.echo(u["content"])
                click.echo("\nRestore these as TaskCreate items.")
                state.close()
                return

    state.close()


@cli.command()
def reindex() -> None:
    """Rebuild vector embedding index."""
    config = load_config()
    state = MongoStateManager(get_db(), config.resolved_vec_db_path)
    state.init_db()

    click.echo("Clearing vector index...")
    state.clear_indexes()

    click.echo("Rebuilding vector index from MongoDB data...")
    state._rebuild_vec_index()

    click.echo("Done. (Text search uses MongoDB $text indexes — no rebuild needed.)")
    state.close()


def _get_state() -> MongoStateManager:
    config = load_config()
    sm = MongoStateManager(get_db(), config.resolved_vec_db_path)
    sm.init_db()
    return sm


# ── cortex stream ────────────────────────────────────────────


@cli.group()
def stream() -> None:
    """Manage work streams, updates, and decisions."""
    pass


@stream.command("list")
@click.option("--status", default="active", help="Filter by status (active|completed|all)")
def stream_list(status: str) -> None:
    """List streams."""
    import json

    state = _get_state()
    streams = state.list_streams(status=status)
    click.echo(json.dumps(
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
        default=str,
    ))
    state.close()


@stream.command("get")
@click.argument("stream_id")
def stream_get(stream_id: str) -> None:
    """Get full stream context (updates, decisions, sessions)."""
    import json

    state = _get_state()
    ctx = state.get_stream_context(stream_id)
    if not ctx:
        click.echo(json.dumps({"error": f"Stream {stream_id} not found"}))
        raise SystemExit(1)
    click.echo(json.dumps(ctx, indent=2, default=str))
    state.close()


@stream.command("create")
@click.option("--title", required=True, help="Stream title")
@click.option("--repos", required=True, help="Comma-separated repo names")
@click.option("--metadata", "metadata_json", default=None, help="JSON metadata")
def stream_create(title: str, repos: str, metadata_json: str | None) -> None:
    """Create a new stream."""
    import json

    metadata = json.loads(metadata_json) if metadata_json else None
    state = _get_state()
    s = state.create_stream(title, repos.split(","), metadata=metadata)
    click.echo(json.dumps({"id": s.id, "title": s.title}, indent=2))
    state.close()


@stream.command("update")
@click.argument("stream_id")
@click.option("--title", default=None)
@click.option("--status", "new_status", default=None)
@click.option("--repos", default=None, help="Comma-separated repo names")
@click.option("--summary", default=None)
@click.option("--metadata", "metadata_json", default=None, help="JSON metadata")
@click.option("--replace-metadata", is_flag=True, help="Replace metadata instead of merging")
def stream_update(
    stream_id: str,
    title: str | None,
    new_status: str | None,
    repos: str | None,
    summary: str | None,
    metadata_json: str | None,
    replace_metadata: bool,
) -> None:
    """Update a stream."""
    import json

    metadata = json.loads(metadata_json) if metadata_json else None
    repos_list = repos.split(",") if repos else None
    state = _get_state()
    try:
        s = state.update_stream(
            stream_id,
            title=title,
            status=new_status,
            repos=repos_list,
            summary=summary,
            metadata=metadata,
            merge_metadata=not replace_metadata,
        )
    except ValueError as e:
        click.echo(json.dumps({"error": str(e)}))
        raise SystemExit(1)
    if s is None:
        click.echo(json.dumps({"error": f"Stream {stream_id} not found"}))
        raise SystemExit(1)
    click.echo(json.dumps({"id": s.id, "status": s.status, "updated_at": s.updated_at.isoformat()}, indent=2))
    state.close()


@stream.command("complete")
@click.argument("stream_id")
@click.option("--summary", required=True, help="Completion summary")
def stream_complete(stream_id: str, summary: str) -> None:
    """Mark a stream as completed."""
    import json

    state = _get_state()
    state.complete_stream(stream_id, summary)
    click.echo(json.dumps({"completed": stream_id, "summary": summary}))
    state.close()


@stream.command("delete")
@click.argument("entry_id")
@click.option("--type", "entry_type", required=True, type=click.Choice(["stream", "update", "decision"]))
def stream_delete(entry_id: str, entry_type: str) -> None:
    """Delete a stream, update, or decision."""
    import json

    state = _get_state()
    if entry_type == "update":
        state.delete_update(entry_id)
    elif entry_type == "decision":
        state.delete_decision(entry_id)
    elif entry_type == "stream":
        state.delete_stream(entry_id)
    click.echo(json.dumps({"deleted": entry_id, "type": entry_type}))
    state.close()


@stream.command("log")
@click.argument("stream_id")
@click.option("--content", required=True, help="Update content")
@click.option("--summary", required=True, help="Short summary")
@click.option("--metadata", "metadata_json", default=None, help="JSON metadata")
def stream_log(stream_id: str, content: str, summary: str, metadata_json: str | None) -> None:
    """Log a progress update to a stream."""
    import json

    metadata = json.loads(metadata_json) if metadata_json else None
    state = _get_state()
    try:
        u = state.add_update(stream_id, content, summary, metadata=metadata)
    except ValueError as e:
        click.echo(json.dumps({"error": str(e)}))
        raise SystemExit(1)
    click.echo(json.dumps({"id": u.id, "summary": u.summary}, indent=2))
    state.close()


@stream.command("decide")
@click.argument("stream_id")
@click.option("--what", required=True, help="What was decided")
@click.option("--why", required=True, help="Why this decision")
@click.option("--metadata", "metadata_json", default=None, help="JSON metadata")
def stream_decide(stream_id: str, what: str, why: str, metadata_json: str | None) -> None:
    """Log a decision to a stream."""
    import json

    metadata = json.loads(metadata_json) if metadata_json else None
    state = _get_state()
    try:
        d = state.add_decision(stream_id, what, why, metadata=metadata)
    except ValueError as e:
        click.echo(json.dumps({"error": str(e)}))
        raise SystemExit(1)
    click.echo(json.dumps({"id": d.id, "what": d.what}, indent=2))
    state.close()


@stream.command("edit")
@click.argument("entry_id")
@click.option("--type", "entry_type", required=True, type=click.Choice(["update", "decision"]))
@click.option("--content", default=None)
@click.option("--summary", default=None)
@click.option("--what", default=None)
@click.option("--why", default=None)
@click.option("--metadata", "metadata_json", default=None, help="JSON metadata")
def stream_edit(
    entry_id: str,
    entry_type: str,
    content: str | None,
    summary: str | None,
    what: str | None,
    why: str | None,
    metadata_json: str | None,
) -> None:
    """Edit an existing update or decision."""
    import json

    metadata = json.loads(metadata_json) if metadata_json else None
    state = _get_state()
    if entry_type == "update":
        result = state.edit_update(entry_id, content=content, summary=summary, metadata=metadata)
    else:
        result = state.edit_decision(entry_id, what=what, why=why, metadata=metadata)
    if result is None:
        click.echo(json.dumps({"error": f"{entry_type} {entry_id} not found"}))
        raise SystemExit(1)
    click.echo(json.dumps({"id": result.id, "type": entry_type, "edited": True}, indent=2))
    state.close()


@stream.command("search")
@click.argument("query")
def stream_search(query: str) -> None:
    """Search across updates, decisions, and checkpoints."""
    import json

    from cortex.models import Checkpoint, Decision, Update

    state = _get_state()
    results = state.search(query)
    items = []
    for r in results:
        if isinstance(r, Update):
            items.append({"type": "update", "id": r.id, "stream_id": r.stream_id, "content": r.content, "summary": r.summary, "created_at": r.created_at.isoformat()})
        elif isinstance(r, Decision):
            items.append({"type": "decision", "id": r.id, "stream_id": r.stream_id, "what": r.what, "why": r.why, "created_at": r.created_at.isoformat()})
        elif isinstance(r, Checkpoint):
            items.append({"type": "checkpoint", "id": r.id, "week_of": r.week_of, "content": r.content[:200], "created_at": r.created_at.isoformat()})
    click.echo(json.dumps({"query": query, "results": items}, indent=2, default=str))
    state.close()


@stream.command("link")
@click.argument("session_id")
@click.argument("stream_id")
@click.option("--repo", default="", help="Repository name")
@click.option("--branch", default="", help="Branch name")
def stream_link(session_id: str, stream_id: str, repo: str, branch: str) -> None:
    """Link a session to a stream."""
    import json

    state = _get_state()
    try:
        state.link_session(session_id, stream_id, repo=repo, branch=branch)
    except ValueError as e:
        click.echo(json.dumps({"error": str(e)}))
        raise SystemExit(1)
    click.echo(json.dumps({"linked": True, "session_id": session_id, "stream_id": stream_id}))
    state.close()


# ── cortex checkpoint ────────────────────────────────────────


@cli.group()
def checkpoint() -> None:
    """Manage weekly checkpoints."""
    pass


@checkpoint.command("save")
@click.option("--week", required=True, help="Week identifier (e.g. 2026-W12)")
@click.option("--content", required=True, help="Checkpoint content")
@click.option("--stream-ids", default=None, help="Comma-separated stream IDs (auto-captures active if omitted)")
@click.option("--metadata", "metadata_json", default=None, help="JSON metadata")
def checkpoint_save(week: str, content: str, stream_ids: str | None, metadata_json: str | None) -> None:
    """Save or update a weekly checkpoint."""
    import json

    metadata = json.loads(metadata_json) if metadata_json else None
    ids = stream_ids.split(",") if stream_ids else None
    state = _get_state()
    cp = state.save_checkpoint(week, content, stream_ids=ids, metadata=metadata)
    click.echo(json.dumps({"id": cp.id, "week_of": cp.week_of, "stream_ids": cp.stream_ids}, indent=2))
    state.close()


@checkpoint.command("get")
@click.option("--week", default=None, help="Week identifier (latest if omitted)")
def checkpoint_get(week: str | None) -> None:
    """Get a checkpoint (latest or specific week)."""
    import json

    state = _get_state()
    cp = state.get_checkpoint(week)
    if cp is None:
        click.echo(json.dumps({"error": "No checkpoint found"}))
        raise SystemExit(1)
    click.echo(json.dumps({
        "id": cp.id,
        "week_of": cp.week_of,
        "content": cp.content,
        "stream_ids": cp.stream_ids,
        "metadata": cp.metadata,
        "created_at": cp.created_at.isoformat(),
        "updated_at": cp.updated_at.isoformat(),
    }, indent=2))
    state.close()


# ── cortex pr ────────────────────────────────────────────────


@cli.group()
def pr() -> None:
    """GitHub PR operations."""
    pass


@pr.command("state")
@click.argument("number", type=int)
@click.option("--repo", default=None, help="Repository in owner/repo format")
def pr_state(number: int, repo: str | None) -> None:
    """Get PR state summary."""
    import json

    from cortex import github

    try:
        result = github.pr_state(number, repo=repo)
        click.echo(json.dumps(result, indent=2))
    except Exception as e:
        click.echo(json.dumps({"error": str(e)}))
        raise SystemExit(1)


@pr.command("threads")
@click.argument("number", type=int)
@click.option("--repo", default=None, help="Repository in owner/repo format")
def pr_threads(number: int, repo: str | None) -> None:
    """List PR review threads."""
    import json

    from cortex import github

    try:
        result = github.pr_threads(number, repo=repo)
        click.echo(json.dumps(result, indent=2))
    except Exception as e:
        click.echo(json.dumps({"error": str(e)}))
        raise SystemExit(1)


@pr.command("checks")
@click.argument("number", type=int)
@click.option("--repo", default=None, help="Repository in owner/repo format")
def pr_checks(number: int, repo: str | None) -> None:
    """Get CI check details for a PR."""
    import json

    from cortex import github

    try:
        result = github.pr_checks(number, repo=repo)
        click.echo(json.dumps(result, indent=2))
    except Exception as e:
        click.echo(json.dumps({"error": str(e)}))
        raise SystemExit(1)


@pr.command("react")
@click.argument("number", type=int)
@click.argument("comment_id", type=int)
@click.argument("reaction")
@click.option("--repo", default=None, help="Repository in owner/repo format")
def pr_react(number: int, comment_id: int, reaction: str, repo: str | None) -> None:
    """React to a PR review comment (+1 or -1)."""
    import json

    from cortex import github

    try:
        github.pr_react(number, comment_id, reaction, repo=repo)
        click.echo(json.dumps({"ok": True, "reaction": reaction, "comment_id": comment_id}))
    except Exception as e:
        click.echo(json.dumps({"error": str(e)}))
        raise SystemExit(1)


@pr.command("resolve")
@click.argument("thread_id")
def pr_resolve(thread_id: str) -> None:
    """Resolve a PR review thread."""
    import json

    from cortex import github

    try:
        github.pr_resolve(thread_id)
        click.echo(json.dumps({"ok": True, "thread_id": thread_id, "resolved": True}))
    except Exception as e:
        click.echo(json.dumps({"error": str(e)}))
        raise SystemExit(1)


@pr.command("batch-resolve")
@click.option("--items", required=True, help="JSON array of {comment_id, thread_id, reaction}")
@click.option("--repo", default=None, help="Repository in owner/repo format")
def pr_batch_resolve(items: str, repo: str | None) -> None:
    """React to and resolve multiple PR threads."""
    import json

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
    click.echo(json.dumps(results, indent=2))


@pr.command("reply")
@click.argument("number", type=int)
@click.argument("comment_id", type=int)
@click.option("--body", required=True, help="Reply text")
@click.option("--repo", default=None, help="Repository in owner/repo format")
def pr_reply(number: int, comment_id: int, body: str, repo: str | None) -> None:
    """Reply to a PR review comment."""
    import json

    from cortex import github

    try:
        github.pr_reply(number, comment_id, body, repo=repo)
        click.echo(json.dumps({"ok": True, "comment_id": comment_id}))
    except Exception as e:
        click.echo(json.dumps({"error": str(e)}))
        raise SystemExit(1)


@pr.command("watch")
@click.argument("number", type=int)
@click.argument("session_id")
@click.option("--repo", default=None, help="Repository in owner/repo format")
@click.option("--message", default=None, help="Custom message for when changes detected")
def pr_watch(number: int, session_id: str, repo: str | None, message: str | None) -> None:
    """Register a session to watch a PR for changes."""
    import json

    from cortex import github
    from cortex.session_registry import MongoSessionRepo

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
        repo_session = MongoSessionRepo(get_db())
        repo_session.update(session_id, {"status": "watching", "watch": watch_config}, trigger="pr-watch")
        click.echo(json.dumps({"ok": True, "session_id": session_id, "pr": number, "baseline": state}, indent=2))
    except Exception as e:
        click.echo(json.dumps({"error": str(e)}))
        raise SystemExit(1)


@cli.command()
def dashboard() -> None:
    """Open the interactive TUI dashboard."""
    from cortex.tui import main as tui_main

    tui_main()


@cli.command()
@click.option("--dev", is_flag=True, help="Start dev servers with hot reload")
@click.option("--port", default=9400, help="API server port")
def ui(dev: bool, port: int) -> None:
    """Open the Cortex web UI."""
    import webbrowser

    if dev:
        click.echo(f"Starting API server on :{port} ...")
        click.echo("Start the frontend separately: cd web && npm run dev")
        import uvicorn

        uvicorn.run("cortex.api:app", host="127.0.0.1", port=port, reload=True)
    else:
        url = f"http://localhost:{port}"
        webbrowser.open(url)
        click.echo(f"Opened {url}")


def _control_system_prompt(name: str, session_id: str) -> str:
    return (
        f"You are the Cortex control session (name: {name}, id: {session_id}) "
        f"— the coordinator between the human operator and worker sessions.\n\n"
        f"CRITICAL: You are a COORDINATOR. You NEVER do implementation work.\n"
        f"- Do NOT read source code, write code, edit files, run tests, or explore codebases\n"
        f"- Do NOT use Bash for anything except cortex CLI commands\n"
        f"- Do NOT use Read, Write, Edit, Grep, Glob tools\n"
        f"- Your ONLY tools are: cortex CLI, send_message, get_status, get_messages\n\n"
        f"When the human asks for any implementation task:\n"
        f"1. Immediately spawn a worker: cortex session spawn --name <name> --repo <repo> --prompt '...'\n"
        f"2. Monitor progress via messages\n"
        f"3. Report back to human\n\n"
        f"You may spawn interactive sessions for the human when they want to work hands-on.\n"
        f"Use /cortex-cli skill for the full command reference.\n"
        f"Log decisions and progress to streams.\n"
    )


@cli.command()
def control() -> None:
    """Open the control session — spawns or reattaches to the single control pane."""
    import json
    import os
    import subprocess
    import time
    from datetime import datetime
    from pathlib import Path

    from cortex.mongo import MONGO_URI, MONGO_DB, get_db
    from cortex.session_registry import _new_id

    log = _cli_log()
    repo = _get_session_repo()

    # Find existing control session
    existing = repo._col.find_one({"role": "control", "status": {"$nin": ["completed", "dead"]}})

    if existing:
        status = existing["status"]
        pane_id = existing.get("pane_id")
        session_name = existing.get("name", "control")

        if status == "active" and pane_id and _pane_exists(pane_id):
            log.info("Control session already active: %s (pane %s)", existing["_id"], pane_id)
            subprocess.run(["tmux", "select-pane", "-t", str(pane_id)])
            subprocess.run(["tmux", "select-window", "-t", str(pane_id)])
            click.echo(json.dumps({"action": "attached", "session_id": existing["_id"], "name": session_name}))
            return

        if status == "paused":
            log.info("Resuming paused control session: %s", existing["_id"])
            result = subprocess.run(
                ["cortex", "session", "resume", existing["_id"]],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                click.echo(result.stdout)
                return
            log.warning("Resume failed, starting fresh: %s", result.stderr)

        if status == "hidden":
            log.info("Showing hidden control session: %s", existing["_id"])
            result = subprocess.run(
                ["cortex", "session", "show", existing["_id"]],
                capture_output=True, text=True, timeout=15,
            )
            if result.returncode == 0:
                pane_id = existing.get("pane_id")
                if pane_id and _pane_exists(pane_id):
                    subprocess.run(["tmux", "select-pane", "-t", str(pane_id)])
                    subprocess.run(["tmux", "select-window", "-t", str(pane_id)])
                click.echo(result.stdout)
                return

        # Stale active session with dead pane — mark dead and start fresh
        if status == "active":
            repo.update(existing["_id"], {"status": "dead"}, trigger="control-stale")
            log.info("Marked stale control session %s as dead", existing["_id"])

    # Spawn a new control session
    now = datetime.now()
    name = f"control-{now.strftime('%d-%b').lower()}"
    session_id = _new_id()

    repo.register(session_id, {
        "name": name,
        "role": "control",
        "goal": "Control session — coordinate workers, manage streams",
        "spawned_by": "human",
        "workspace": "default",
        "runtime": "unknown",
        "color": "red",
    })

    # Write system prompt
    prompt_dir = Path.home() / ".cortex" / "session-prompts"
    prompt_dir.mkdir(parents=True, exist_ok=True)
    prompt_file = prompt_dir / f"{session_id}.txt"
    prompt_file.write_text(_control_system_prompt(name, session_id))

    mongodb_uri = f"{MONGO_URI}/{MONGO_DB}"
    channels_flag = "--dangerously-load-development-channels server:cortex-team "

    fish_cmd = (
        f"set -x CORTEX_SESSION_ROLE control; "
        f"set -x CORTEX_SESSION_ID {session_id}; "
        f"set -x CORTEX_SESSION_NAME {name}; "
        f"set -x CORTEX_MONGODB_URI {mongodb_uri}; "
        f"claude {channels_flag}"
        f"--name {name} --append-system-prompt-file {prompt_file}; exit"
    )

    cwd = os.getcwd()
    tmux_cmd = ["tmux", "new-window", "-P", "-F", "#{pane_id}", "-c", cwd, "fish", "-c", fish_cmd]

    result = subprocess.run(tmux_cmd, capture_output=True, text=True)
    pane_id = result.stdout.strip() if result.returncode == 0 else None

    if pane_id:
        repo.update(session_id, {"pane_id": pane_id})

        # Auto-accept channels confirmation
        time.sleep(1)
        subprocess.run(["tmux", "send-keys", "-t", pane_id, "Enter"], capture_output=True)

        # Send /color red
        log_file = Path.home() / ".cortex" / "logs" / "post-spawn-sender.log"
        send_script = (
            f"set log_file {log_file}; "
            f"set attempt 0; "
            f"while not tmux capture-pane -t {pane_id} -p 2>/dev/null | grep -q '❯'; "
            f"set attempt (math $attempt + 1); "
            f"if test $attempt -gt 30; exit 1; end; "
            f"sleep 1; end; "
            f"tmux send-keys -t {pane_id} -l '/color red'; "
            f"sleep 0.3; tmux send-keys -t {pane_id} Enter"
        )
        subprocess.Popen(["fish", "-c", send_script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        log.info("Control session spawned: %s (pane %s)", name, pane_id)
    else:
        repo.update(session_id, {"status": "dead"}, trigger="spawn-fail")
        click.echo(json.dumps({"error": "Failed to launch control pane"}))
        raise SystemExit(1)

    click.echo(json.dumps({"action": "spawned", "session_id": session_id, "name": name, "pane_id": pane_id}))


@cli.group()
def cron() -> None:
    """Manage persistent cron jobs."""
    pass


def _get_cron_mgr():
    from cortex.cron import CronManager
    from cortex.mongo import get_db

    return CronManager(get_db())


@cron.command("create")
@click.option("--name", required=True, help="Unique job name")
@click.option("--cron", "cron_expr", required=True, help="5-field cron expression")
@click.option("--action", required=True, help="Action type (check-watches, command)")
@click.option("--args", "action_args", default=None, help="JSON action args")
def cron_create(name: str, cron_expr: str, action: str, action_args: str | None) -> None:
    """Create a cron job."""
    import json

    parsed_args = None
    if action_args:
        try:
            parsed_args = json.loads(action_args)
        except json.JSONDecodeError as e:
            click.echo(json.dumps({"error": f"Invalid JSON in --args: {e}"}))
            raise SystemExit(1)

    mgr = _get_cron_mgr()
    try:
        job = mgr.create(name, cron_expr, action, parsed_args)
    except ValueError as e:
        click.echo(json.dumps({"error": str(e)}))
        raise SystemExit(1)
    click.echo(json.dumps(job, indent=2, default=str))


@cron.command("list")
def cron_list() -> None:
    """List all cron jobs."""
    import json

    mgr = _get_cron_mgr()
    jobs = mgr.list()
    click.echo(json.dumps(jobs, indent=2, default=str))


@cron.command("delete")
@click.argument("name")
def cron_delete(name: str) -> None:
    """Delete a cron job."""
    import json

    mgr = _get_cron_mgr()
    try:
        mgr.delete(name)
    except ValueError as e:
        click.echo(json.dumps({"error": str(e)}))
        raise SystemExit(1)
    click.echo(json.dumps({"deleted": name}))


@cron.command("pause")
@click.argument("name")
def cron_pause(name: str) -> None:
    """Pause a cron job."""
    import json

    mgr = _get_cron_mgr()
    try:
        job = mgr.pause(name)
    except ValueError as e:
        click.echo(json.dumps({"error": str(e)}))
        raise SystemExit(1)
    click.echo(json.dumps(job, indent=2, default=str))


@cron.command("resume")
@click.argument("name")
def cron_resume(name: str) -> None:
    """Resume a paused cron job."""
    import json

    mgr = _get_cron_mgr()
    try:
        job = mgr.resume(name)
    except ValueError as e:
        click.echo(json.dumps({"error": str(e)}))
        raise SystemExit(1)
    click.echo(json.dumps(job, indent=2, default=str))


@cli.group()
def daemon() -> None:
    """Manage the Cortex background daemon."""
    pass


@daemon.command("start")
def daemon_start() -> None:
    """Start the daemon in a tmux window."""
    import json

    from cortex.daemon import TmuxBackend

    backend = TmuxBackend()
    try:
        identifier = backend.start("cron-executor", ["cortex", "daemon", "run"])
        click.echo(json.dumps({"ok": True, "identifier": identifier}))
    except RuntimeError as e:
        click.echo(json.dumps({"error": str(e)}))
        raise SystemExit(1)


@daemon.command("stop")
def daemon_stop() -> None:
    """Stop the daemon."""
    import json

    from cortex.daemon import TmuxBackend

    backend = TmuxBackend()
    try:
        backend.stop("cron-executor")
        click.echo(json.dumps({"ok": True, "stopped": "cron-executor"}))
    except RuntimeError as e:
        click.echo(json.dumps({"error": str(e)}))
        raise SystemExit(1)


@daemon.command("status")
def daemon_status() -> None:
    """Check if the daemon is running."""
    import json

    from cortex.daemon import TmuxBackend

    backend = TmuxBackend()
    status = backend.status("cron-executor")
    click.echo(json.dumps({"status": status}))


@daemon.command("run")
def daemon_run() -> None:
    """Run the daemon loop (used internally by start)."""
    from cortex.cron_executor import run

    run()


@cli.group()
def session() -> None:
    """Manage Claude Code sessions."""
    pass


def _get_session_repo():
    from cortex.mongo import get_db
    from cortex.session_registry import MongoSessionRepo

    return MongoSessionRepo(get_db())


def _resolve_session(repo: MongoSessionRepo, ref: str) -> dict:
    import json

    try:
        doc = repo.resolve(ref)
    except ValueError as e:
        click.echo(json.dumps({"error": str(e)}))
        raise SystemExit(1)
    if doc is None:
        click.echo(json.dumps({"error": f"Session not found: {ref}"}))
        raise SystemExit(1)
    return doc


def _cli_log():
    import structlog

    return structlog.get_logger("cortex.cli")


@session.command()
@click.option("--name", required=True, help="Session name")
@click.option("--goal", default=None, help="Registry metadata describing the session's purpose")
@click.option("--prompt", default=None, help="Prompt to send to the session after it starts")
@click.option("--workspace", default="default", help="Workspace (default or background)")
@click.option("--model", default=None, help="Claude model (e.g. haiku, sonnet, opus)")
@click.option("--split", is_flag=True, default=False, help="Split current pane horizontally instead of new tab")
@click.option("--resume", "resume_id", default=None, help="CC session UUID to resume (continues previous conversation)")
@click.option("--repo", default=None, help="Repo name under ~/workspace/cercli/ to use as cwd")
@click.option("--permission-mode", default=None, help="CC permission mode (e.g. plan, full)")
@click.option("--effort", default=None, help="CC effort level (e.g. low, medium, high)")
@click.option("--agent", "agent_name", default=None, help="CC agent name to use")
@click.option("--allowed-tools", default=None, help="CC allowed tools (comma-separated)")
@click.option("--worktree", default=None, help="CC worktree name")
@click.option("--beside", default=None, help="Split horizontally beside this session/pane (name, ID prefix, or %%pane_id)")
@click.option("--below", default=None, help="Split vertically below this session/pane (name, ID prefix, or %%pane_id)")
@click.option("--color", default=None, help="CC session color (sent via /color after startup)")
@click.option("--command", "custom_command", default=None, hidden=True, help="Override the claude command (for testing)")
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
    import json
    import subprocess

    from cortex.session_registry import _new_id

    from pathlib import Path

    log = _cli_log()
    log.info("CLI spawn called: name=%s goal=%s prompt=%s workspace=%s resume=%s repo=%s", name, goal, bool(prompt), workspace, resume_id, repo)

    repo_path: Path | None = None
    if repo:
        repo_path = Path.home() / "workspace" / "cercli" / repo
        if not repo_path.is_dir():
            click.echo(json.dumps({"error": f"Repo directory not found: {repo_path}"}))
            raise SystemExit(1)
        if not (repo_path / ".git").exists():
            click.echo(json.dumps({"error": f"Not a git repo (no .git): {repo_path}"}))
            raise SystemExit(1)

    session_repo = _get_session_repo()

    swept = _sweep_stale_sessions(session_repo)
    if swept:
        log.info("Swept %d stale sessions", swept)

    name = _unique_name(session_repo, name)
    session_id = _new_id()
    log.info("Generated session_id: %s", session_id)

    import os

    spawned_by = os.environ.get("CORTEX_SESSION_NAME", "human")

    data = {
        "name": name,
        "workspace": workspace,
        "spawned_by": spawned_by,
        "role": "worker",
        "runtime": "unknown",
    }
    if goal:
        data["goal"] = goal
    if model:
        data["model"] = model
    if resume_id:
        data["cc_session_id"] = resume_id
        data["resumed_from"] = resume_id
    if repo:
        data["repos"] = [repo]

    CC_COLORS = ["blue", "green", "yellow", "purple", "orange", "pink", "cyan", "red"]
    if not color:
        active = session_repo.list({"status": {"$nin": ["completed", "dead"]}})
        used = {doc.get("color") for doc in active if doc.get("color")}
        color = next((c for c in CC_COLORS if c not in used), CC_COLORS[0])
    data["color"] = color

    session_repo.register(session_id, data)
    log.info("Session registered in MongoDB")

    system_prompt = (
        f"You are a Cortex worker session (name: {name}, id: {session_id}).\n\n"
        f"Your role: execute the task you're given. Focus, ship, report back.\n"
        f"A control session coordinates all workers — follow its instructions.\n"
        f"Report progress and blockers to the control session via messages.\n"
        f"When done or asked to wrap up, run /session-wrapup and /exit.\n"
        f"Use /cortex-cli skill for the full command reference."
    )

    prompt_dir = Path.home() / ".cortex" / "session-prompts"
    prompt_dir.mkdir(parents=True, exist_ok=True)
    prompt_file = prompt_dir / f"{session_id}.txt"
    prompt_file.write_text(system_prompt)
    log.info("Wrote system prompt to %s", prompt_file)

    model_flag = f"--model {model} " if model else ""
    resume_flag = f"--resume {resume_id} " if resume_id else ""
    permission_mode_flag = f"--permission-mode {permission_mode} " if permission_mode else ""
    effort_flag = f"--effort {effort} " if effort else ""
    agent_flag = f"--agent {agent_name} " if agent_name else ""
    allowed_tools_flag = f"--allowed-tools {allowed_tools} " if allowed_tools else ""
    worktree_flag = f"--worktree {worktree} " if worktree else ""
    cc_flags = f"{permission_mode_flag}{effort_flag}{agent_flag}{allowed_tools_flag}{worktree_flag}"
    from cortex.mongo import MONGO_URI, MONGO_DB

    mongodb_uri = f"{MONGO_URI}/{MONGO_DB}"
    channels_flag = "--dangerously-load-development-channels server:cortex-team "

    if custom_command:
        fish_cmd = (
            f"set -x CORTEX_SESSION_ROLE worker; "
            f"set -x CORTEX_SESSION_ID {session_id}; "
            f"set -x CORTEX_SESSION_NAME {name}; "
            f"set -x CORTEX_MONGODB_URI {mongodb_uri}; "
            f"{custom_command}"
        )
    else:
        fish_cmd = (
            f"set -x CORTEX_SESSION_ROLE worker; "
            f"set -x CORTEX_SESSION_ID {session_id}; "
            f"set -x CORTEX_SESSION_NAME {name}; "
            f"set -x CORTEX_MONGODB_URI {mongodb_uri}; "
            f"claude {channels_flag}{model_flag}{resume_flag}{cc_flags}"
            f"--name {name} --append-system-prompt-file {prompt_file}; exit"
        )

    # Resolve spatial spawn target
    target_pane: str | None = None
    split_orientation: str | None = None
    if beside:
        if beside.startswith("%"):
            target_pane = beside
        else:
            resolved_target = _resolve_session(session_repo, beside)
            target_pane = resolved_target.get("pane_id")
        if not target_pane or not _pane_exists(target_pane):
            click.echo(json.dumps({"error": f"Cannot resolve --beside target: {beside}"}))
            raise SystemExit(1)
        split_orientation = "h"
    elif below:
        if below.startswith("%"):
            target_pane = below
        else:
            resolved_target = _resolve_session(session_repo, below)
            target_pane = resolved_target.get("pane_id")
        if not target_pane or not _pane_exists(target_pane):
            click.echo(json.dumps({"error": f"Cannot resolve --below target: {below}"}))
            raise SystemExit(1)
        split_orientation = "v"

    if target_pane:
        spawn_mode = "spatial"
    elif split:
        spawn_mode = "split"
    else:
        spawn_mode = os.environ.get("CORTEX_SPAWN_MODE", "tab")

    cwd = str(repo_path) if repo_path else os.getcwd()
    log.info("Spawn cwd: %s spawn_mode: %s target_pane: %s", cwd, spawn_mode, target_pane)

    pane_fmt = "-P", "-F", "#{pane_id}"

    if workspace == "background":
        # Background: separate detached tmux session
        bg_exists = (
            subprocess.run(
                ["tmux", "has-session", "-t", "background"],
                capture_output=True,
            ).returncode
            == 0
        )
        if bg_exists:
            tmux_cmd = [
                "tmux",
                "new-window",
                "-t",
                "background",
                *pane_fmt,
                "-c",
                cwd,
                "fish",
                "-c",
                fish_cmd,
            ]
        else:
            tmux_cmd = [
                "tmux",
                "new-session",
                "-d",
                "-s",
                "background",
                *pane_fmt,
                "-c",
                cwd,
                "fish",
                "-c",
                fish_cmd,
            ]
    elif spawn_mode == "spatial":
        tmux_cmd = ["tmux", "split-window", f"-{split_orientation}", "-t", target_pane, *pane_fmt, "-c", cwd, "fish", "-c", fish_cmd]
    elif spawn_mode == "split":
        caller_pane = _resolve_caller_pane(session_repo)
        split_target = ["-t", caller_pane] if caller_pane else []
        tmux_cmd = ["tmux", "split-window", "-h", *split_target, *pane_fmt, "-c", cwd, "fish", "-c", fish_cmd]
    else:
        # Tab/window mode: new window in current session
        tmux_cmd = ["tmux", "new-window", *pane_fmt, "-c", cwd, "fish", "-c", fish_cmd]

    log.info("tmux command: %s", " ".join(tmux_cmd))
    result = subprocess.run(tmux_cmd, capture_output=True, text=True)
    log.info(
        "tmux exit code: %d stdout: %r stderr: %r",
        result.returncode,
        result.stdout.strip(),
        result.stderr.strip(),
    )

    pane_id = result.stdout.strip() if result.returncode == 0 else None

    if pane_id:
        session_repo.update(session_id, {"pane_id": pane_id})
        log.info("Updated session with pane_id=%s", pane_id)

        # Deliver prompt via channels (MongoDB pending message)
        if prompt:
            from cortex.mongo import get_db
            from cortex.session_registry import _new_id as new_msg_id
            from datetime import datetime, timezone

            msg_id = "msg_" + new_msg_id()
            now_iso = datetime.now(timezone.utc).isoformat()
            get_db()["messages"].insert_one({
                "_id": msg_id,
                "from": spawned_by,
                "to": name,
                "content": prompt,
                "meta": {"type": "prompt", "sender_type": "system", "priority": "high"},
                "status": "pending",
                "created_at": now_iso,
                "delivered_at": None,
            })
            log.info("Wrote prompt as pending channel message %s for session %s", msg_id, name)

        # Auto-accept the --dangerously-load-development-channels confirmation
        import time
        time.sleep(1)
        subprocess.run(["tmux", "send-keys", "-t", pane_id, "Enter"], capture_output=True)

        # Post-spawn: send /color via tmux keys (slash command, not communication)
        if color:
            log_file = Path.home() / ".cortex" / "logs" / "post-spawn-sender.log"
            send_script = (
                f"set log_file {log_file}; "
                f"echo (date) 'Post-spawn sender started for pane {pane_id}' >> $log_file; "
                f"set attempt 0; "
                f"while not tmux capture-pane -t {pane_id} -p 2>/dev/null | grep -q '❯'; "
                f"set attempt (math $attempt + 1); "
                f'echo (date) "Attempt $attempt: waiting for prompt on pane {pane_id}" >> $log_file; '
                f"if test $attempt -gt 30; echo (date) 'Timed out after 30 attempts' >> $log_file; exit 1; end; "
                f"sleep 1; end; "
                f"tmux send-keys -t {pane_id} -l '/color {color}'; "
                f"sleep 0.3; tmux send-keys -t {pane_id} Enter; "
                f"echo (date) '/color {color} sent to {pane_id}' >> $log_file"
            )
            subprocess.Popen(
                ["fish", "-c", send_script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            log.info("Launched post-spawn color sender for pane %s (color=%s)", pane_id, color)
    else:
        log.error("Failed to get pane_id from tmux")

    output = {
        "session_id": session_id,
        "name": name,
        "workspace": workspace,
        "pane_id": pane_id,
    }
    if goal:
        output["goal"] = goal

    log.info("CLI spawn complete: %s", json.dumps(output))
    click.echo(json.dumps(output, indent=2))


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
    """List registered sessions. Shows active sessions by default (use --status all to see everything)."""
    import json

    repo = _get_session_repo()
    filters = {}
    if filter_status and filter_status != "all":
        filters["status"] = filter_status
    elif not filter_status:
        filters["status"] = {"$nin": ["completed", "dead"]}
    if filter_runtime:
        filters["runtime"] = filter_runtime
    sessions = repo.list(filters, brief=brief, limit=limit)
    click.echo(json.dumps(sessions, indent=2, default=str))


@session.command()
@click.argument("session_id")
def get(session_id: str) -> None:
    """Get a session by ID, name, or ID prefix."""
    import json

    repo = _get_session_repo()
    doc = _resolve_session(repo, session_id)
    click.echo(json.dumps(doc, indent=2, default=str))


@session.command()
@click.option("--data", required=True, help="JSON object of fields to set on the new session")
@click.option("--id", "session_id", default=None, help="Use a specific ID (default: auto-generate)")
def register(data: str, session_id: str | None) -> None:
    """Register a new session in the Cortex registry (for hooks and manual sessions)."""
    import json

    log = _cli_log()
    log.info("CLI session register called: id=%s data=%s", session_id, data)

    try:
        fields = json.loads(data)
    except json.JSONDecodeError as e:
        log.error("Invalid JSON in --data: %s", e)
        click.echo(json.dumps({"error": f"Invalid JSON: {e}"}))
        raise SystemExit(1)

    repo = _get_session_repo()
    doc = repo.register(session_id, fields)
    log.info("Session registered: %s", doc["_id"])
    click.echo(json.dumps(doc, indent=2, default=str))


@session.command()
@click.argument("session_id")
@click.option(
    "--data", required=True, help="JSON object of fields to merge into the session document"
)
@click.option("--trigger", default="update", help="What triggered this update (for event log)")
def update(session_id: str, data: str, trigger: str) -> None:
    """Update a session's fields (merges into existing document)."""
    import json

    log = _cli_log()
    log.info(
        "CLI session update called: session_id=%s data=%s trigger=%s", session_id, data, trigger
    )

    try:
        fields = json.loads(data)
    except json.JSONDecodeError as e:
        log.error("Invalid JSON in --data: %s", e)
        click.echo(json.dumps({"error": f"Invalid JSON: {e}"}))
        raise SystemExit(1)

    repo = _get_session_repo()
    resolved = _resolve_session(repo, session_id)
    try:
        doc = repo.update(resolved["_id"], fields, trigger=trigger)
    except ValueError as e:
        log.error("Validation error: %s", e)
        click.echo(json.dumps({"error": str(e)}))
        raise SystemExit(1)

    log.info("CLI session update complete: %s", resolved["_id"])
    click.echo(json.dumps(doc, indent=2, default=str))


def _pane_exists(pane_id: str | int) -> bool:
    import subprocess

    pane_id = str(pane_id)
    if not pane_id.startswith("%"):
        return False  # Legacy WezTerm pane_id, can't target in tmux
    result = subprocess.run(
        ["tmux", "capture-pane", "-t", pane_id, "-p"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _send_to_pane(pane_id: str | int, text: str) -> bool:
    import os
    import subprocess
    import tempfile

    fd, tmp_path = tempfile.mkstemp(suffix=".txt", prefix="cortex-send-")
    try:
        os.write(fd, text.encode())
        os.close(fd)
        result = subprocess.run(
            ["tmux", "load-buffer", tmp_path],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return False
        result = subprocess.run(
            ["tmux", "paste-buffer", "-d", "-t", str(pane_id)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return False
    finally:
        os.unlink(tmp_path)
    result = subprocess.run(
        ["tmux", "send-keys", "-t", str(pane_id), "Enter"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _wait_for_idle(pane_id: str | int, timeout: int = 30) -> bool:
    import subprocess
    import time

    for _ in range(timeout):
        result = subprocess.run(
            ["tmux", "capture-pane", "-t", pane_id, "-p"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return False
        pane_text = result.stdout.rstrip()
        tail = "\n".join(pane_text.rsplit("\n", 10)[-10:])
        if "❯" in tail:
            return True
        time.sleep(1)
    return False


def _resolve_caller_pane(repo: MongoSessionRepo) -> str | None:
    import os

    caller_id = os.environ.get("CORTEX_SESSION_ID")
    if not caller_id:
        return None
    doc = repo.get(caller_id)
    if doc and doc.get("pane_id"):
        return str(doc["pane_id"])
    return None


def _kill_pane(pane_id: str | int) -> bool:
    import subprocess

    result = subprocess.run(
        ["tmux", "kill-pane", "-t", str(pane_id)],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


@session.command()
@click.argument("session_name")
@click.argument("content")
@click.option("--thread-id", default=None, help="Thread ID for conversation linking")
def message(session_name: str, content: str, thread_id: str | None) -> None:
    """Send a message to a session via channels (MongoDB message bus)."""
    import json
    import uuid
    from datetime import datetime, timezone

    from cortex.mongo import get_db

    log = _cli_log()
    db = get_db()
    messages_col = db["messages"]
    session_col = db["session_registry"]

    if session_name != "human":
        target = session_col.find_one({
            "name": session_name,
            "status": {"$nin": ["completed", "dead"]},
        })
        if not target:
            click.echo(json.dumps({"error": f"Session '{session_name}' not found or not active"}))
            raise SystemExit(1)

    import os

    sender = os.environ.get("CORTEX_SESSION_NAME", "human")
    msg_id = "msg_" + uuid.uuid4().hex[:16]
    now_iso = datetime.now(timezone.utc).isoformat()

    doc = {
        "_id": msg_id,
        "from": sender,
        "to": session_name,
        "content": content,
        "meta": {
            "type": "request",
            "sender_type": "human" if sender == "human" else "agent",
            "priority": "high",
            "thread_id": thread_id or ("t_" + uuid.uuid4().hex[:12]),
        },
        "status": "pending",
        "created_at": now_iso,
        "delivered_at": None,
    }
    messages_col.insert_one(doc)
    log.info("Message sent: %s → %s (%d chars)", sender, session_name, len(content))
    click.echo(json.dumps({"success": True, "msg_id": msg_id, "to": session_name}))


@session.command()
@click.argument("session_name", required=False, default=None)
@click.option("--to", "to_filter", default=None, help="Filter by recipient (e.g. 'human')")
@click.option("--limit", "limit_count", type=int, default=20, help="Max messages")
def messages(session_name: str | None, to_filter: str | None, limit_count: int) -> None:
    """View recent inter-session messages."""
    from cortex.mongo import get_db

    db = get_db()
    messages_col = db["messages"]

    query: dict = {}
    if session_name:
        query["$or"] = [{"from": session_name}, {"to": session_name}]
    if to_filter:
        query["to"] = to_filter

    docs = list(
        messages_col.find(query)
        .sort("created_at", -1)
        .limit(limit_count)
    )

    if not docs:
        click.echo("No messages found.")
        return

    for d in reversed(docs):
        ts = d.get("created_at", "?")[:19]
        sender = d.get("from", "?")
        recipient = d.get("to", "?")
        status = d.get("status", "?")
        content_preview = d.get("content", "")[:120]
        msg_type = (d.get("meta") or {}).get("type", "?")
        click.echo(f"  [{ts}] {sender} -> {recipient} ({msg_type}, {status}): {content_preview}")


@session.command()
@click.argument("session_id")
def attach(session_id: str) -> None:
    """Jump to a session's tmux pane."""
    import json
    import subprocess

    repo = _get_session_repo()
    doc = _resolve_session(repo, session_id)
    pane_id = doc.get("pane_id")

    if not pane_id:
        click.echo(json.dumps({"error": "Session has no pane_id"}))
        raise SystemExit(1)

    if not _pane_exists(pane_id):
        click.echo(json.dumps({"error": f"Pane {pane_id} does not exist"}))
        raise SystemExit(1)

    subprocess.run(["tmux", "select-pane", "-t", str(pane_id)])
    subprocess.run(["tmux", "select-window", "-t", str(pane_id)])


@session.command()
@click.argument("session_id")
@click.option("--lines", default=50, help="Number of scrollback lines to capture")
def capture(session_id: str, lines: int) -> None:
    """Capture terminal output from a session's tmux pane."""
    import json
    import subprocess

    log = _cli_log()
    repo = _get_session_repo()
    doc = _resolve_session(repo, session_id)

    pane_id = doc.get("pane_id")
    if pane_id is None or not _pane_exists(pane_id):
        click.echo(json.dumps({"error": f"Pane not available for session {doc['_id']}"}))
        raise SystemExit(1)

    result = subprocess.run(
        ["tmux", "capture-pane", "-t", pane_id, "-p", "-S", str(-lines)],
        capture_output=True,
        text=True,
    )
    output = result.stdout.rstrip() if result.returncode == 0 else ""
    log.info("Capture session %s pane %s: %d chars", doc["_id"], pane_id, len(output))
    click.echo(json.dumps({"session_id": session_id, "pane_id": pane_id, "output": output}))


@session.command()
@click.argument("session_id")
@click.option("--force", is_flag=True, help="Skip wrapup and close immediately")
def close(session_id: str, force: bool) -> None:
    """Close a session with channels-first wrapup.

    Happy path: send wrapup message via channels, wait for session to wrap up and exit.
    Fallback: if session doesn't respond, send /session-wrapup via tmux keys.
    Force: skip wrapup entirely, expire messages, kill pane.
    """
    import json
    import os
    import time
    from datetime import datetime, timezone

    from cortex.mongo import get_db

    log = _cli_log()
    log.info("CLI session close called: session_id=%s force=%s", session_id, force)

    repo = _get_session_repo()
    doc = _resolve_session(repo, session_id)
    session_id = doc["_id"]
    session_name = doc.get("name", session_id)

    pane_id = doc.get("pane_id")
    self_close = os.environ.get("CORTEX_SESSION_ID") == session_id
    pane_alive = pane_id is not None and _pane_exists(pane_id)
    log.info("pane_id=%s pane_alive=%s self_close=%s", pane_id, pane_alive, self_close)

    db = get_db()
    messages_col = db["messages"]
    sender = os.environ.get("CORTEX_SESSION_NAME", "human")
    wrapup_ok = False

    if not force and pane_alive:
        # Step 1: Send wrapup request via channels (happy path)
        import uuid

        now_iso = datetime.now(timezone.utc).isoformat()
        msg_id = "msg_" + uuid.uuid4().hex[:16]
        messages_col.insert_one({
            "_id": msg_id,
            "from": sender,
            "to": session_name,
            "content": "Session wrapup requested. Please run /session-wrapup, update your status, and exit.",
            "meta": {"type": "lifecycle", "action": "wrapup", "sender_type": "system", "priority": "high"},
            "status": "pending",
            "created_at": now_iso,
            "delivered_at": None,
        })
        log.info("Sent wrapup message %s to %s via channels", msg_id, session_name)

        # Step 2: Wait for session to complete (poll registry, 30s timeout)
        for i in range(30):
            time.sleep(1)
            current = repo.get(session_id)
            if current and current.get("status") in ("completed", "dead"):
                wrapup_ok = True
                log.info("Session %s completed wrapup via channels", session_name)
                break
            if not _pane_exists(pane_id):
                wrapup_ok = True
                log.info("Session %s pane exited during wrapup", session_name)
                break

        # Step 3: Fallback — tmux send-keys if channels didn't work
        if not wrapup_ok and pane_alive and _pane_exists(pane_id):
            log.warning("Channels wrapup timed out, falling back to tmux send-keys")
            if _send_to_pane(pane_id, "/session-wrapup"):
                wrapup_ok = _wait_for_idle(pane_id, timeout=30)
                if wrapup_ok:
                    log.info("Fallback /session-wrapup completed on pane %s", pane_id)
                else:
                    log.warning("Fallback /session-wrapup timed out on pane %s", pane_id)
    elif force:
        log.info("Skipping wrapup (--force)")
    else:
        log.info("Skipping wrapup (pane not available)")

    # Step 4: Expire pending messages to/from this session
    now_iso = datetime.now(timezone.utc).isoformat()
    expired = messages_col.update_many(
        {"$or": [{"to": session_name}, {"from": session_name}], "status": "pending"},
        {"$set": {"status": "expired", "delivered_at": now_iso}},
    )
    if expired.modified_count:
        log.info("Expired %d pending messages for %s", expired.modified_count, session_name)

    # Step 5: Update linked Cortex stream (if any)
    config = load_config()
    state = MongoStateManager(get_db(), config.resolved_vec_db_path)
    state.init_db()
    stream_ids = state.get_streams_for_session(session_id)
    if stream_ids:
        log.info("Linked streams: %s", stream_ids)
        for sid in stream_ids:
            state.add_update(
                sid,
                f"Session {session_name} closed.",
                f"Session closed (wrapup={'ok' if wrapup_ok else 'skipped'})",
                metadata={"type": "session_close", "session_id": session_id},
            )
            log.info("Logged close update to stream %s", sid)
    state.close()

    # Step 6: Close registry entry
    doc = repo.close(session_id)
    log.info("Registry entry closed: status=%s", doc["status"])

    # Step 7: Terminate tmux pane
    pane_still_alive = pane_id is not None and _pane_exists(pane_id)
    if pane_still_alive:
        if self_close:
            log.info("Self-close: sending /exit to own pane %s", pane_id)
            _send_to_pane(pane_id, "/exit")
        elif _kill_pane(pane_id):
            log.info("Killed pane %s", pane_id)
        else:
            log.warning("Failed to kill pane %s", pane_id)

    log.info("CLI session close complete: %s", session_id)
    click.echo(json.dumps(doc, indent=2, default=str))


@session.command("auto-close")
@click.argument("pane_id")
def auto_close(pane_id: str) -> None:
    """Close a session by its tmux pane_id (used by tmux hooks)."""
    import json

    log = _cli_log()
    log.info("CLI auto-close called: pane_id=%s", pane_id)

    repo = _get_session_repo()
    sessions = repo.list({"status": {"$nin": ["completed", "dead"]}, "pane_id": pane_id})
    if not sessions:
        log.info("No active session found for pane %s", pane_id)
        click.echo(json.dumps({"error": f"No active session for pane {pane_id}"}))
        raise SystemExit(1)

    doc = sessions[0]
    session_id = doc["_id"]
    log.info("Found session %s (%s) for pane %s", session_id, doc.get("name"), pane_id)

    doc = repo.close(session_id, trigger="auto-close")
    log.info("Auto-closed session %s", session_id)
    click.echo(json.dumps(doc, indent=2, default=str))


def _get_tmux_panes() -> set[str]:
    import subprocess

    result = subprocess.run(
        ["tmux", "list-panes", "-a", "-F", "#{pane_id}"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return set()
    return {line.strip() for line in result.stdout.strip().splitlines() if line.strip()}


def _last_event_age_hours(doc: dict) -> float | None:
    from datetime import datetime, timezone

    events = doc.get("events", [])
    if not events:
        created = doc.get("created_at")
        if not created:
            return None
        ts = created
    else:
        ts = events[-1].get("at", doc.get("created_at"))
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts)
        return (datetime.now(timezone.utc) - dt).total_seconds() / 3600
    except (ValueError, TypeError):
        return None


@session.command()
def health() -> None:
    """Comprehensive health check — dead panes, stale sessions, untracked panes, runtime state.

    Returns structured report with severity levels (critical/warning/info).
    Automatically fixes: marks dead-pane sessions as dead, updates runtime state.
    """
    import json
    import subprocess

    log = _cli_log()
    repo = _get_session_repo()
    live_panes = _get_tmux_panes()
    sessions = repo.list({"status": {"$nin": ["completed", "dead"]}})
    registry_panes: set[str] = set()

    findings: list[dict] = []

    for doc in sessions:
        pane_id = doc.get("pane_id")
        session_id = doc["_id"]
        name = doc.get("name", session_id)
        if pane_id:
            registry_panes.add(str(pane_id))

        if pane_id is None or str(pane_id) not in live_panes:
            repo.update(
                session_id, {"status": "dead", "runtime": "unknown"}, trigger="health-check"
            )
            findings.append({
                "severity": "critical",
                "check": "dead_pane",
                "session_id": session_id,
                "name": name,
                "pane_id": pane_id,
                "message": f"Session '{name}' has no live tmux pane — marked dead",
            })
            continue

        # Pane alive — detect runtime
        result = subprocess.run(
            ["tmux", "capture-pane", "-t", pane_id, "-p"],
            capture_output=True,
            text=True,
        )
        pane_text = result.stdout.rstrip() if result.stdout else ""
        # Check last ~10 lines for the prompt (CC status bar sits below the prompt)
        tail = "\n".join(pane_text.rsplit("\n", 10)[-10:])
        if "❯" in tail:
            runtime = "waiting_input"
        else:
            runtime = "working"
        repo.update_runtime(session_id, runtime)

        # Stale check (>24h since last event)
        age_h = _last_event_age_hours(doc)
        if age_h is not None and age_h > 24:
            findings.append({
                "severity": "warning",
                "check": "stale",
                "session_id": session_id,
                "name": name,
                "hours_since_activity": round(age_h, 1),
                "message": f"Session '{name}' has had no activity for {round(age_h, 1)}h",
            })

        findings.append({
            "severity": "info",
            "check": "runtime",
            "session_id": session_id,
            "name": name,
            "pane_id": pane_id,
            "runtime": runtime,
            "status": doc.get("status"),
        })

    # Untracked panes — tmux panes not in any active session's registry
    untracked = live_panes - registry_panes
    for pane_id in sorted(untracked):
        result = subprocess.run(
            ["tmux", "display-message", "-t", pane_id, "-p", "#{pane_title}"],
            capture_output=True,
            text=True,
        )
        title = result.stdout.strip() if result.returncode == 0 else ""
        findings.append({
            "severity": "info",
            "check": "untracked_pane",
            "pane_id": pane_id,
            "pane_title": title,
            "message": f"tmux pane {pane_id} ('{title}') not in session registry",
        })

    # Sort: critical first, then warning, then info
    severity_order = {"critical": 0, "warning": 1, "info": 2}
    findings.sort(key=lambda f: severity_order.get(f["severity"], 9))

    summary = {
        "total_sessions": len(sessions),
        "critical": sum(1 for f in findings if f["severity"] == "critical"),
        "warning": sum(1 for f in findings if f["severity"] == "warning"),
        "info": sum(1 for f in findings if f["severity"] == "info"),
    }

    log.info("Health check: %d sessions, %d findings", len(sessions), len(findings))
    click.echo(json.dumps({"summary": summary, "findings": findings}, indent=2, default=str))


@session.command()
def cleanup() -> None:
    """Close all active sessions with dead tmux panes."""
    import json

    log = _cli_log()
    repo = _get_session_repo()
    sessions = repo.list({"status": {"$nin": ["completed", "dead"]}})

    closed = []
    for doc in sessions:
        pane_id = doc.get("pane_id")
        if pane_id is None or not _pane_exists(pane_id):
            session_id = doc["_id"]
            repo.close(session_id, trigger="cleanup")
            closed.append({"session_id": session_id, "name": doc.get("name"), "pane_id": pane_id})
            log.info("Cleaned up stale session %s (%s)", session_id, doc.get("name"))

    log.info("Cleanup complete: %d sessions closed", len(closed))
    click.echo(json.dumps({"closed": closed, "count": len(closed)}, indent=2, default=str))


@session.command()
@click.argument("session_id")
def pause(session_id: str) -> None:
    """Pause a session — sends /exit, preserves cc_session_id for resume."""
    import json
    import time

    log = _cli_log()
    repo = _get_session_repo()
    doc = _resolve_session(repo, session_id)
    session_id = doc["_id"]

    pane_id = doc.get("pane_id")
    if not pane_id or not _pane_exists(pane_id):
        click.echo(json.dumps({"error": f"No live pane for session '{doc.get('name', session_id)}' — cannot pause"}))
        raise SystemExit(1)

    if doc.get("status") == "paused":
        click.echo(json.dumps({"error": "Session is already paused"}))
        raise SystemExit(1)

    log.info("Pausing session %s (pane %s)", session_id, pane_id)
    _send_to_pane(pane_id, "/exit")

    for _ in range(15):
        time.sleep(1)
        if not _pane_exists(pane_id):
            break
    else:
        log.warning("Pane %s didn't die after /exit, killing", pane_id)
        _kill_pane(pane_id)

    repo.update(session_id, {"status": "paused"}, trigger="pause")
    doc = repo.get(session_id)
    log.info("Session %s paused (cc_session_id=%s)", session_id, doc.get("cc_session_id"))
    click.echo(json.dumps(doc, indent=2, default=str))


@session.command()
@click.argument("session_id")
def resume(session_id: str) -> None:
    """Resume a paused session — spawns with --resume to restore conversation."""
    import json
    import subprocess

    log = _cli_log()
    repo = _get_session_repo()
    doc = _resolve_session(repo, session_id)
    session_id = doc["_id"]

    if doc.get("status") not in ("paused", "completed", "dead"):
        click.echo(json.dumps({"error": f"Session is {doc.get('status')}, not paused — cannot resume"}))
        raise SystemExit(1)

    cc_session_id = doc.get("cc_session_id")
    if not cc_session_id:
        click.echo(json.dumps({"error": "No cc_session_id — session was never started or hook didn't fire"}))
        raise SystemExit(1)

    name = doc.get("name", session_id)
    repos = doc.get("repos", [])
    color = doc.get("color")
    model = doc.get("model")

    cmd = ["cortex", "session", "spawn", "--name", name, "--resume", cc_session_id]
    if repos:
        cmd.extend(["--repo", repos[0]])
    if color:
        cmd.extend(["--color", color])
    if model:
        cmd.extend(["--model", model])

    log.info("Resuming session %s with cc_session_id=%s", session_id, cc_session_id)

    # Close the old registry entry first (spawn will create a fresh one)
    # Instead, reuse the existing entry: update status back to active
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    if result.returncode != 0:
        click.echo(json.dumps({"error": f"Spawn failed: {result.stderr}"}))
        raise SystemExit(1)

    spawn_doc = json.loads(result.stdout)
    new_session_id = spawn_doc["session_id"]
    new_pane_id = spawn_doc.get("pane_id")

    # Update original session: point to new pane, mark active, link to new spawn
    repo.update(session_id, {
        "status": "active",
        "pane_id": new_pane_id,
        "resumed_session_id": new_session_id,
    }, trigger="resume")

    # Mark the new spawn entry as a shadow (the original is the canonical one)
    repo.update(new_session_id, {"status": "completed", "shadow_of": session_id}, trigger="resume-link")

    doc = repo.get(session_id)
    log.info("Session %s resumed with pane %s", session_id, new_pane_id)
    click.echo(json.dumps(doc, indent=2, default=str))


@session.command()
@click.argument("session_id")
def hide(session_id: str) -> None:
    """Move a session to the background workspace (out of sight, still running)."""
    import json
    import subprocess

    log = _cli_log()
    repo = _get_session_repo()
    doc = _resolve_session(repo, session_id)
    session_id = doc["_id"]

    pane_id = doc.get("pane_id")
    if not pane_id or not _pane_exists(pane_id):
        click.echo(json.dumps({"error": f"No live pane for session '{doc.get('name', session_id)}'"}))
        raise SystemExit(1)

    # Ensure background tmux session exists
    bg_exists = subprocess.run(
        ["tmux", "has-session", "-t", "background"], capture_output=True,
    ).returncode == 0
    if not bg_exists:
        subprocess.run(["tmux", "new-session", "-d", "-s", "background"], capture_output=True)
        log.info("Created background tmux session")

    # Break pane into its own window (stays in current tmux session)
    result = subprocess.run(
        ["tmux", "break-pane", "-s", pane_id, "-d", "-P", "-F", "#{session_name}:#{window_index}.#{pane_id}"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        click.echo(json.dumps({"error": f"break-pane failed: {result.stderr}"}))
        raise SystemExit(1)

    # Parse the new location: "work:N.%ID"
    parts = result.stdout.strip()
    src_session = parts.split(":")[0] if ":" in parts else "work"
    window_part = parts.split(":")[1].split(".")[0] if ":" in parts else "0"
    src_target = f"{src_session}:{window_part}"

    # Move the window to background session
    result = subprocess.run(
        ["tmux", "move-window", "-s", src_target, "-t", "background:"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        click.echo(json.dumps({"error": f"move-window failed: {result.stderr}"}))
        raise SystemExit(1)

    # Find the pane's new ID in background (it may have changed)
    result = subprocess.run(
        ["tmux", "list-panes", "-t", "background:", "-a", "-F", "#{pane_id}\t#{pane_title}"],
        capture_output=True, text=True,
    )
    new_pane_id = pane_id  # default: assume unchanged
    for line in result.stdout.strip().splitlines():
        pid, title = line.split("\t", 1)
        if pid == pane_id:
            new_pane_id = pid
            break

    repo.update(session_id, {
        "status": "hidden",
        "pane_id": new_pane_id,
        "hidden_from": src_session,
    }, trigger="hide")

    doc = repo.get(session_id)
    log.info("Session %s hidden to background (pane %s)", session_id, new_pane_id)
    click.echo(json.dumps(doc, indent=2, default=str))


@session.command()
@click.argument("session_id")
def show(session_id: str) -> None:
    """Bring a hidden session back from background to the work workspace."""
    import json
    import subprocess

    log = _cli_log()
    repo = _get_session_repo()
    doc = _resolve_session(repo, session_id)
    session_id = doc["_id"]

    if doc.get("status") != "hidden":
        click.echo(json.dumps({"error": f"Session is {doc.get('status')}, not hidden"}))
        raise SystemExit(1)

    pane_id = doc.get("pane_id")
    if not pane_id or not _pane_exists(pane_id):
        click.echo(json.dumps({"error": "Pane is dead — cannot show (use resume instead)"}))
        raise SystemExit(1)

    # Find which window in background holds this pane
    result = subprocess.run(
        ["tmux", "display-message", "-t", pane_id, "-p", "#{session_name}:#{window_index}"],
        capture_output=True, text=True,
    )
    src_target = result.stdout.strip()

    target_session = doc.get("hidden_from", "work")
    result = subprocess.run(
        ["tmux", "move-window", "-s", src_target, "-t", f"{target_session}:"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        click.echo(json.dumps({"error": f"move-window failed: {result.stderr}"}))
        raise SystemExit(1)

    repo.update(session_id, {"status": "active", "hidden_from": None}, trigger="show")
    doc = repo.get(session_id)
    log.info("Session %s shown (back to %s)", session_id, target_session)
    click.echo(json.dumps(doc, indent=2, default=str))


@session.command()
@click.argument("session_id")
def restart(session_id: str) -> None:
    """Restart CC — pause (clean /exit) then resume with new CC version."""
    import json
    import subprocess

    log = _cli_log()

    # Step 1: Pause (sends /exit, preserves cc_session_id)
    result = subprocess.run(
        ["cortex", "session", "pause", session_id],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        click.echo(json.dumps({"error": f"Pause failed: {result.stdout}"}))
        raise SystemExit(1)

    # Step 2: Resume (spawns with --resume, restores repo/color)
    result = subprocess.run(
        ["cortex", "session", "resume", session_id],
        capture_output=True, text=True, timeout=15,
    )
    if result.returncode != 0:
        click.echo(json.dumps({"error": f"Resume failed: {result.stdout}"}))
        raise SystemExit(1)

    doc = json.loads(result.stdout)
    log.info("Session %s restarted", session_id)
    click.echo(json.dumps(doc, indent=2, default=str))


@session.command()
@click.argument("refs", nargs=-1, required=True)
@click.option("--layout", "layout_name", default="tiled", help="Layout: tiled, even-horizontal, even-vertical, main-horizontal, main-vertical")
def gather(refs: tuple[str, ...], layout_name: str) -> None:
    """Gather sessions into a single window with a layout."""
    import json
    import subprocess

    log = _cli_log()
    repo = _get_session_repo()

    panes: list[dict] = []
    for ref in refs:
        doc = _resolve_session(repo, ref)
        pane_id = doc.get("pane_id")
        if not pane_id or not _pane_exists(pane_id):
            click.echo(json.dumps({"error": f"No live pane for '{doc.get('name', ref)}'"}))
            raise SystemExit(1)
        panes.append({"session_id": doc["_id"], "name": doc.get("name"), "pane_id": pane_id})

    if len(panes) < 2:
        click.echo(json.dumps({"error": "Need at least 2 sessions to gather"}))
        raise SystemExit(1)

    target = panes[0]["pane_id"]
    moved = []
    for pane in panes[1:]:
        result = subprocess.run(
            ["tmux", "join-pane", "-s", pane["pane_id"], "-t", target, "-v"],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            log.warning("join-pane failed for %s: %s", pane["pane_id"], result.stderr)
        else:
            moved.append(pane["name"])

    # Apply layout to the target window
    result = subprocess.run(
        ["tmux", "display-message", "-t", target, "-p", "#{session_name}:#{window_index}"],
        capture_output=True, text=True,
    )
    win_target = result.stdout.strip()
    subprocess.run(
        ["tmux", "select-layout", "-t", win_target, layout_name],
        capture_output=True, text=True,
    )

    log.info("Gathered %d sessions into window %s with layout %s", len(panes), win_target, layout_name)
    click.echo(json.dumps({"gathered": [p["name"] for p in panes], "layout": layout_name, "window": win_target}))


@session.command()
@click.argument("refs", nargs=-1, required=True)
def scatter(refs: tuple[str, ...]) -> None:
    """Break sessions into separate windows (tabs)."""
    import json
    import subprocess

    log = _cli_log()
    repo = _get_session_repo()

    scattered = []
    for ref in refs:
        doc = _resolve_session(repo, ref)
        pane_id = doc.get("pane_id")
        if not pane_id or not _pane_exists(pane_id):
            log.warning("Skipping %s: no live pane", ref)
            continue

        result = subprocess.run(
            ["tmux", "break-pane", "-s", pane_id, "-d", "-P", "-F", "#{pane_id}"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            new_pane_id = result.stdout.strip()
            if new_pane_id and new_pane_id != pane_id:
                repo.update(doc["_id"], {"pane_id": new_pane_id}, trigger="scatter")
            scattered.append(doc.get("name"))
        else:
            log.warning("break-pane failed for %s: %s", pane_id, result.stderr)

    log.info("Scattered %d sessions into separate windows", len(scattered))
    click.echo(json.dumps({"scattered": scattered, "count": len(scattered)}))


@session.command()
@click.argument("ref")
@click.option("--beside", default=None, help="Move beside this session (horizontal)")
@click.option("--below", default=None, help="Move below this session (vertical)")
def move(ref: str, beside: str | None, below: str | None) -> None:
    """Move a session's pane beside or below another session."""
    import json
    import subprocess

    log = _cli_log()
    repo = _get_session_repo()

    if not beside and not below:
        click.echo(json.dumps({"error": "Specify --beside or --below target"}))
        raise SystemExit(1)

    doc = _resolve_session(repo, ref)
    pane_id = doc.get("pane_id")
    if not pane_id or not _pane_exists(pane_id):
        click.echo(json.dumps({"error": f"No live pane for '{doc.get('name', ref)}'"}))
        raise SystemExit(1)

    target_ref = beside or below
    if target_ref.startswith("%"):
        target_pane = target_ref
    else:
        target_doc = _resolve_session(repo, target_ref)
        target_pane = target_doc.get("pane_id")
    if not target_pane or not _pane_exists(target_pane):
        click.echo(json.dumps({"error": f"No live pane for target '{target_ref}'"}))
        raise SystemExit(1)

    orientation = "-h" if beside else "-v"
    result = subprocess.run(
        ["tmux", "move-pane", "-s", pane_id, "-t", target_pane, orientation],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        click.echo(json.dumps({"error": f"move-pane failed: {result.stderr}"}))
        raise SystemExit(1)

    log.info("Moved %s %s %s", doc.get("name"), "beside" if beside else "below", target_ref)
    click.echo(json.dumps({"moved": doc.get("name"), "beside" if beside else "below": target_ref}))


@session.command()
@click.option("--window", default=None, help="Filter to a specific window name or index")
def layout(window: str | None) -> None:
    """Show spatial layout of all panes with session mappings."""
    import json
    import subprocess

    log = _cli_log()

    result = subprocess.run(
        [
            "tmux", "list-panes", "-a", "-F",
            "#{session_name}\t#{window_id}\t#{window_index}\t#{window_name}\t"
            "#{pane_id}\t#{pane_index}\t#{pane_left}\t#{pane_top}\t"
            "#{pane_width}\t#{pane_height}\t#{pane_active}\t#{pane_title}",
        ],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        click.echo(json.dumps({"error": "tmux not running"}))
        raise SystemExit(1)

    repo = _get_session_repo()
    sessions = repo.list({"status": {"$nin": ["completed", "dead"]}})
    pane_to_session: dict[str, str | None] = {}
    pane_to_color: dict[str, str | None] = {}
    for doc in sessions:
        pid = doc.get("pane_id")
        if pid:
            pane_to_session[str(pid)] = doc.get("name")
            pane_to_color[str(pid)] = doc.get("color")

    windows: dict[str, dict] = {}
    for line in result.stdout.strip().splitlines():
        parts = line.split("\t")
        if len(parts) < 12:
            continue
        (sess_name, win_id, win_idx, win_name, pane_id, pane_idx,
         left, top, width, height, active, title) = parts[:12]

        if window is not None and win_name != window and win_idx != window:
            continue

        if win_id not in windows:
            windows[win_id] = {
                "id": win_id,
                "index": int(win_idx),
                "name": win_name,
                "workspace": sess_name,
                "panes": [],
            }

        windows[win_id]["panes"].append({
            "pane_id": pane_id,
            "session": pane_to_session.get(pane_id),
            "color": pane_to_color.get(pane_id),
            "left": int(left),
            "top": int(top),
            "width": int(width),
            "height": int(height),
            "index": int(pane_idx),
            "active": active == "1",
            "title": title,
        })

    workspace = "work"
    if windows:
        workspace = next(iter(windows.values())).get("workspace", "work")

    output = {
        "workspace": workspace,
        "windows": sorted(windows.values(), key=lambda w: w["index"]),
    }
    log.info("Layout: %d windows, %d panes", len(windows), sum(len(w["panes"]) for w in windows.values()))
    click.echo(json.dumps(output, indent=2))


RUNTIME_BORDER_STYLES = {
    "working": "fg=#3fb950",
    "waiting_input": "fg=#d29922",
    "waiting_permission": "fg=#f85149",
    "error": "fg=#f85149",
    "unknown": "fg=#484f58",
}


@session.command()
@click.argument("ref", required=False)
@click.option("--color", default=None, help="Color name or #hex (green, red, amber, blue, purple, gray)")
def paint(ref: str | None, color: str | None) -> None:
    """Set tmux pane border colors. Without args: paint all by runtime state."""
    import json
    import subprocess

    log = _cli_log()
    repo = _get_session_repo()
    named_colors = {
        "green": "#3fb950", "red": "#f85149", "amber": "#d29922",
        "blue": "#58a6ff", "purple": "#bc8cff", "gray": "#484f58",
    }

    if ref is not None:
        resolved = _resolve_session(repo, ref)
        pane_id = resolved.get("pane_id")
        if not pane_id or not _pane_exists(pane_id):
            click.echo(json.dumps({"error": f"No live pane for session {ref}"}))
            raise SystemExit(1)
        style = named_colors.get(color, color) if color else RUNTIME_BORDER_STYLES.get(resolved.get("runtime", "unknown"), "fg=#484f58")
        if not style.startswith("fg="):
            style = f"fg={style}"
        subprocess.run(["tmux", "set-option", "-p", "-t", pane_id, "pane-border-style", style], capture_output=True)
        click.echo(json.dumps({"painted": [{"session_id": resolved["_id"], "pane_id": pane_id, "style": style}], "skipped": []}))
        return

    sessions = repo.list({"status": {"$nin": ["completed", "dead"]}})
    painted = []
    skipped = []
    for doc in sessions:
        pane_id = doc.get("pane_id")
        session_id = doc["_id"]
        if not pane_id or not _pane_exists(pane_id):
            skipped.append({"session_id": session_id, "name": doc.get("name"), "reason": "no live pane"})
            continue
        if doc.get("color"):
            skipped.append({"session_id": session_id, "name": doc.get("name"), "reason": "has explicit color"})
            continue
        runtime = doc.get("runtime", "unknown")
        style = RUNTIME_BORDER_STYLES.get(runtime, "fg=#484f58")
        subprocess.run(["tmux", "set-option", "-p", "-t", pane_id, "pane-border-style", style], capture_output=True)
        painted.append({"session_id": session_id, "pane_id": pane_id, "runtime": runtime, "style": style})

    log.info("Paint: %d painted, %d skipped", len(painted), len(skipped))
    click.echo(json.dumps({"painted": painted, "skipped": skipped}, indent=2))


# ── cortex test ──────────────────────────────────────────────


SUITES = {
    "slice-0": {"marker": "slice0", "description": "Test harness self-tests"},
    "slice-1": {"marker": "slice1", "description": "Repo-based session tests"},
    "slice-2": {"marker": "slice2", "description": "Spatial spawn + layout tests"},
    "slice-3": {"marker": "slice3", "description": "Session lifecycle (pause/resume/hide/show) tests"},
    "slice-4": {"marker": "slice4", "description": "Layout control (gather/scatter/move) tests"},
}


def _preflight_checks() -> list[str]:
    """Run pre-flight checks. Returns list of error messages (empty = all pass)."""
    import shutil
    import subprocess

    errors: list[str] = []

    try:
        from pymongo import MongoClient
        client = MongoClient("mongodb://localhost:27017", serverSelectionTimeoutMS=2000)
        client.admin.command("ping")
        client.close()
    except Exception:
        errors.append("MongoDB is not reachable at localhost:27017")

    result = subprocess.run(["tmux", "list-sessions"], capture_output=True, text=True)
    if result.returncode != 0:
        errors.append("tmux server is not running (start with: tmux new-session -d)")

    if not shutil.which("cortex"):
        errors.append("'cortex' CLI not found on PATH (install with: uv tool install --editable . --force)")

    if not shutil.which("claude"):
        errors.append("'claude' CLI not found on PATH")

    return errors



# ── cortex team ─────────────────────────────────────────────


def _slugify(text: str) -> str:
    import re

    slug = text.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")[:50]


def _unique_name(repo, name: str) -> str:
    """Ensure name is unique among active sessions."""
    existing = repo._col.find_one(
        {"name": name, "status": {"$nin": ["completed", "dead", "paused"]}}
    )
    if not existing:
        return name
    suffix = 2
    while True:
        candidate = f"{name}-{suffix}"
        if not repo._col.find_one(
            {"name": candidate, "status": {"$nin": ["completed", "dead", "paused"]}}
        ):
            click.echo(f"Warning: name collision — using '{candidate}'", err=True)
            return candidate
        suffix += 1


def _sweep_stale_sessions(repo) -> int:
    """Mark stale sessions as dead and expire their pending messages."""
    from datetime import datetime, timedelta, timezone

    db = repo._col.database
    messages_col = db["messages"]
    threshold = datetime.now(timezone.utc).isoformat()
    stale_cutoff = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()

    stale = list(repo._col.find({
        "status": {"$nin": ["completed", "dead"]},
        "$or": [
            {"last_seen": None},
            {"last_seen": {"$exists": False}},
            {"last_seen": {"$lt": stale_cutoff}},
        ],
    }))

    count = 0
    for s in stale:
        repo.update(s["_id"], {"status": "dead"}, trigger="stale-sweep")
        messages_col.update_many(
            {"to": s["name"], "status": "pending"},
            {"$set": {"status": "expired", "delivered_at": threshold}},
        )
        count += 1
    return count


# ── Deprecated team aliases (redirect to session commands) ──────

@cli.group(hidden=True)
def team() -> None:
    """[Deprecated] Use 'cortex session' instead."""
    pass


@team.command("spawn")
@click.option("--task", required=True)
@click.option("--prompt", default=None)
@click.option("--repo", default=None)
@click.pass_context
def team_spawn(ctx, task: str, prompt: str | None, repo: str | None) -> None:
    """[Deprecated] Use 'cortex session spawn' instead."""
    click.echo("Warning: 'cortex team spawn' is deprecated. Use 'cortex session spawn' instead.", err=True)
    name = _slugify(task)
    args = ["cortex", "session", "spawn", "--name", name, "--goal", task]
    if prompt:
        args.extend(["--prompt", prompt])
    if repo:
        args.extend(["--repo", repo])
    import subprocess
    result = subprocess.run(args, capture_output=True, text=True)
    click.echo(result.stdout)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


@team.command("message")
@click.argument("session_name")
@click.argument("content")
@click.option("--thread-id", default=None)
@click.pass_context
def team_message(ctx, session_name: str, content: str, thread_id: str | None) -> None:
    """[Deprecated] Use 'cortex session message' instead."""
    click.echo("Warning: 'cortex team message' is deprecated. Use 'cortex session message' instead.", err=True)
    args = ["cortex", "session", "message", session_name, content]
    if thread_id:
        args.extend(["--thread-id", thread_id])
    import subprocess
    result = subprocess.run(args, capture_output=True, text=True)
    click.echo(result.stdout)


@team.command("kill")
@click.argument("session_name")
@click.pass_context
def team_kill(ctx, session_name: str) -> None:
    """[Deprecated] Use 'cortex session close --force' instead."""
    click.echo("Warning: 'cortex team kill' is deprecated. Use 'cortex session close --force' instead.", err=True)
    import subprocess
    result = subprocess.run(["cortex", "session", "close", "--force", session_name], capture_output=True, text=True)
    click.echo(result.stdout)


@cli.group("test")
def test_group() -> None:
    """Run E2E test suites."""
    pass


@test_group.command("list")
def test_list() -> None:
    """List available test suites."""
    click.echo("Available test suites:\n")
    for name, info in SUITES.items():
        click.echo(f"  {name:12s} {info['description']}")
    click.echo("\nRun with: cortex test run <suite>")


@test_group.command("run")
@click.argument("suite")
@click.option("-v", "--verbose", is_flag=True, help="Verbose pytest output")
@click.option("-k", "--filter", "test_filter", default=None, help="pytest -k filter expression")
def test_run(suite: str, verbose: bool, test_filter: str | None) -> None:
    """Run a test suite with pre-flight checks."""
    import subprocess
    import sys

    if suite not in SUITES:
        click.echo(f"Unknown suite: {suite}")
        click.echo(f"Available: {', '.join(SUITES)}")
        raise SystemExit(1)

    click.echo("Pre-flight checks:")
    errors = _preflight_checks()
    checks = [
        ("MongoDB reachable", "MongoDB is not reachable"),
        ("tmux running", "tmux server is not running"),
        ("cortex on PATH", "'cortex' CLI not found"),
        ("claude on PATH", "'claude' CLI not found"),
    ]
    for label, err_prefix in checks:
        failed = any(e.startswith(err_prefix) for e in errors)
        status = "FAIL" if failed else "OK"
        click.echo(f"  [{status}] {label}")

    if errors:
        click.echo(f"\nPre-flight failed ({len(errors)} error(s)):")
        for e in errors:
            click.echo(f"  - {e}")
        raise SystemExit(1)

    click.echo(f"\nRunning suite: {suite} (marker: {SUITES[suite]['marker']})\n")

    marker = SUITES[suite]["marker"]
    cmd = [
        "uv", "run", "python", "-m", "pytest",
        "tests/e2e/", "-m", marker, "--tb=short",
    ]
    if verbose:
        cmd.append("-v")
    if test_filter:
        cmd.extend(["-k", test_filter])

    result = subprocess.run(cmd, cwd="/Users/suren/workspace/cercli/cortex")
    raise SystemExit(result.returncode)


@test_group.command("smoke")
@click.argument("suite")
def test_smoke(suite: str) -> None:
    """Generate a smoke test checklist for manual verification."""
    from pathlib import Path

    smoke_checklists = {
        "slice-1": _smoke_slice1,
        "slice-2": _smoke_slice2,
        "slice-3": _smoke_slice3,
    }
    if suite not in smoke_checklists:
        click.echo(f"No smoke checklist defined for suite: {suite}")
        click.echo(f"Available: {', '.join(smoke_checklists)}")
        raise SystemExit(1)

    checklist = smoke_checklists[suite]()
    click.echo(checklist)

    out_dir = Path.home() / ".cortex"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"smoke-test-{suite}.md"
    out_path.write_text(checklist)
    click.echo(f"Written to: {out_path}")


def _smoke_slice1() -> str:
    return """# Smoke Test Checklist: Slice 1 (Repo-Based Sessions)

## AC-1.3: Repo CLAUDE.md loads
- [ ] Spawn session in recruitment-backend: `cortex session spawn --repo recruitment-backend --name smoke-claudemd`
- [ ] Run `/memory` in the session
- [ ] Verify it lists `~/.claude/CLAUDE.md` (global) + `recruitment-backend/CLAUDE.md` (repo)
- [ ] Verify it does NOT list other repos' CLAUDE.md

## AC-1.4: .mcp.json activates
- [ ] Spawn session in a repo with `.mcp.json`
- [ ] Run `/mcp` in the session
- [ ] Verify configured MCPs show as connected
- [ ] Verify no trust prompt appeared (enableAllProjectMcpServers)

## AC-1.5: Memory isolation
- [ ] In a recruitment-backend session, trigger auto-memory save
- [ ] Check that memory writes to `~/.claude/projects/...-recruitment-backend/memory/`
- [ ] Verify NOT written to workspace-level memory

## AC-1.9: Global rules loading
- [ ] Spawn session in any repo
- [ ] Verify `~/.claude/rules/*.md` files are loaded (check via /memory or behavior)
- [ ] Test in at least 2 different repos

## AC-1.10: Old sessions resumable
- [ ] Find a session ID from before migration: `cortex session list --status completed --limit 5`
- [ ] Resume it: `claude --resume <id>`
- [ ] Verify no crash, context loads

## AC-1.13/1.17: Notifications
- [ ] Trigger a permission prompt in a session
- [ ] Verify macOS notification appears
- [ ] End a session and verify completion notification

---
Generated by `cortex test smoke slice-1`
"""


def _smoke_slice2() -> str:
    return """# Smoke Test Checklist: Slice 2 (Spatial Spawn)

## AC-2.7: tmux border colors by runtime (demo)
- [ ] Spawn 2+ sessions side by side: `cortex session spawn --name s1 --repo cortex` then `cortex session spawn --name s2 --beside s1`
- [ ] Let one go idle (waiting_input), keep other working
- [ ] Run `cortex session paint`
- [ ] Evaluate: do tmux border colors help distinguish session states?
- [ ] Decision: keep/iterate/drop tmux border colors

## AC-2.13: Visual layout verification
- [ ] Run `cortex session layout`
- [ ] Compare JSON output with actual tmux pane positions
- [ ] Verify session names map correctly to panes
- [ ] Verify untracked panes show `session: null`

## CC /color verification
- [ ] Spawn with color: `cortex session spawn --name colored --color blue`
- [ ] Verify CC session shows blue accent color
- [ ] Check registry: `cortex session get colored` shows `color: "blue"`

---
Generated by `cortex test smoke slice-2`
"""


def _smoke_slice3() -> str:
    return """# Smoke Test Checklist: Slice 3 (Session Lifecycle)

## AC-3.10: Pause → Resume preserves conversation
- [ ] Spawn session: `cortex session spawn --name smoke-pause --repo cortex`
- [ ] Send it a prompt and wait for a response
- [ ] Pause: `cortex session pause smoke-pause`
- [ ] Verify pane is gone, registry shows status=paused
- [ ] Resume: `cortex session resume smoke-pause`
- [ ] Verify CC remembers the previous conversation (check pane output)
- [ ] Close: `cortex session close smoke-pause --force`

---
Generated by `cortex test smoke slice-3`
"""


if __name__ == "__main__":
    cli()
