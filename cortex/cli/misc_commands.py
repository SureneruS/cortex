"""Miscellaneous CLI commands: init, status, brief, link, tasks, reindex,
checkpoint, control, daemon, dashboard, ui, test, deprecated team aliases."""
from __future__ import annotations

import json
import subprocess

import click

from cortex.cli import JsonCommand, JsonGroup, _cli_log, _error_exit, _json_out, _output, get_container
from cortex.config import load_config, save_config, Config, CONFIG_PATH, CORTEX_DIR


def register_misc_commands(cli: click.Group) -> None:
    """Register all miscellaneous commands onto the cli group."""
    cli.add_command(init)
    cli.add_command(status)
    cli.add_command(brief)
    cli.add_command(link)
    cli.add_command(tasks)
    cli.add_command(reindex)
    cli.add_command(checkpoint)
    cli.add_command(control)
    cli.add_command(daemon)
    cli.add_command(logs)
    cli.add_command(errors)
    cli.add_command(dashboard)
    cli.add_command(ui)
    cli.add_command(test_group, "test")
    cli.add_command(team)


# ── Init ─────────────────────────────────────────────────────


@click.command(cls=JsonCommand)
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

    container = get_container()
    svc = container.stream_service
    click.echo("  Database initialized (MongoDB indexes created)")

    click.echo("  Scanning repos for open PRs...")
    from cortex.bootstrap import scan_repos
    stats = scan_repos(config, svc)

    click.echo("\nBootstrap complete:")
    click.echo(f"  Repos scanned: {stats['repos_scanned']}")
    click.echo(f"  Open PRs found: {stats['prs_found']}")
    click.echo(f"  Active branches: {stats['branches_found']}")
    click.echo(f"  Streams created: {stats['streams_created']}")
    if stats["streams_skipped"]:
        click.echo(f"  Streams skipped (already exist): {stats['streams_skipped']}")
    _install_fish_completions()


def _install_fish_completions() -> None:
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


# ── Status / Brief / Link / Tasks / Reindex ──────────────────


@click.command(cls=JsonCommand)
def status() -> None:
    """Show active Cortex streams."""
    svc = get_container().stream_service
    streams = svc.get_active_streams()
    if not streams:
        click.echo("No active streams.")
        return
    for s in streams:
        click.echo(f"  [{s.id}] {s.title}  ({', '.join(s.repos)})")
        if s.summary:
            click.echo(f"          {s.summary}")


@click.command(cls=JsonCommand)
def brief() -> None:
    """Print compact session brief (for hook injection)."""
    svc = get_container().stream_service
    streams = svc.get_active_streams()
    if not streams:
        return
    lines = ["[Cortex] Active streams:"]
    for s in streams[:5]:
        ctx = svc.get_stream_context(s.id)
        recent_decisions = ctx["decisions"][-3:] if ctx["decisions"] else []
        recent_updates = ctx["updates"][-2:] if ctx["updates"] else []
        lines.append(f"  • {s.title} [{', '.join(s.repos)}]")
        for d in recent_decisions:
            lines.append(f"    Decision: {d['what']}")
        for u in recent_updates:
            lines.append(f"    Update: {u['summary']}")
    click.echo("\n".join(lines))


@click.command(cls=JsonCommand)
@click.argument("session_id")
@click.argument("stream_ref")
def link(session_id: str, stream_ref: str) -> None:
    """Link a session to a stream."""
    svc = get_container().stream_service
    stream = svc.resolve_stream(stream_ref)
    if not stream:
        raise SystemExit(f"Stream '{stream_ref}' not found")
    svc.link_session(session_id, stream.id)


@click.command(cls=JsonCommand)
@click.option("--session-id", default=None, help="Claude Code session ID to restore tasks for.")
def tasks(session_id: str | None) -> None:
    """Print pending task backups for session restore."""
    svc = get_container().stream_service
    if session_id:
        stream_ids = svc.get_streams_for_session(session_id)
    else:
        stream_ids = [s.id for s in svc.get_active_streams()]
    if not stream_ids:
        return
    for sid in stream_ids:
        ctx = svc.get_stream_context(sid)
        if not ctx:
            continue
        for u in reversed(ctx["updates"]):
            meta = u.get("metadata") or {}
            if meta.get("type") == "task_backup":
                click.echo(f"[Cortex] Pending tasks from last session (stream: {ctx['stream']['title']}):")
                click.echo(u["content"])
                click.echo("\nRestore these as TaskCreate items.")
                return


@click.command(cls=JsonCommand)
def reindex() -> None:
    """Rebuild vector embedding index."""
    svc = get_container().stream_service
    click.echo("Clearing vector index...")
    svc.clear_indexes()
    click.echo("Rebuilding vector index from MongoDB data...")
    svc.rebuild_vec_index()
    click.echo("Done. (Text search uses MongoDB $text indexes — no rebuild needed.)")


# ── Checkpoint ───────────────────────────────────────────────


@click.group(cls=JsonGroup)
def checkpoint() -> None:
    """Manage weekly checkpoints."""
    pass


@checkpoint.command("save")
@click.option("--week", required=True, help="Week identifier (e.g. 2026-W12)")
@click.option("--content", required=True, help="Checkpoint content")
@click.option("--stream-ids", default=None, help="Comma-separated stream IDs")
@click.option("--metadata", "metadata_json", default=None, help="JSON metadata")
def checkpoint_save(week: str, content: str, stream_ids: str | None, metadata_json: str | None) -> None:
    """Save or update a weekly checkpoint."""
    metadata = json.loads(metadata_json) if metadata_json else None
    ids = stream_ids.split(",") if stream_ids else None
    svc = get_container().stream_service
    cp = svc.save_checkpoint(week, content, stream_ids=ids, metadata=metadata)
    data = {"id": cp.id, "week_of": cp.week_of, "stream_ids": cp.stream_ids}

    def _fmt(d: dict) -> None:
        from cortex.cli.formatters import print_ok
        print_ok(f"Checkpoint saved: {d['week_of']}")

    _output(data, _fmt)


@checkpoint.command("get")
@click.option("--week", default=None, help="Week identifier (latest if omitted)")
def checkpoint_get(week: str | None) -> None:
    """Get a checkpoint (latest or specific week)."""
    cp = get_container().stream_service.get_checkpoint(week)
    if cp is None:
        _error_exit("No checkpoint found")
    data = {
        "id": cp.id, "week_of": cp.week_of, "content": cp.content,
        "stream_ids": cp.stream_ids, "metadata": cp.metadata,
        "created_at": cp.created_at.isoformat(), "updated_at": cp.updated_at.isoformat(),
    }

    def _fmt(d: dict) -> None:
        from cortex.cli.formatters import get_console, print_detail, relative_time, val
        fields = [
            ("Week", val(d.get("week_of"))),
            ("ID", val(d.get("id"))),
            ("Created", relative_time(d.get("created_at"))),
            ("Updated", relative_time(d.get("updated_at"))),
        ]
        if d.get("stream_ids"):
            fields.append(("Streams", ", ".join(d["stream_ids"])))
        print_detail(fields, title=f"Checkpoint {val(d.get('week_of'))}")
        if d.get("content"):
            get_console().print(f"\n{d['content']}")

    _output(data, _fmt)


# ── Control ──────────────────────────────────────────────────


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


@click.command(cls=JsonCommand)
def control() -> None:
    """Open the control session — spawns or reattaches to the single control pane."""
    import os
    import time
    from datetime import datetime
    from pathlib import Path

    from cortex.mongo import MONGO_URI, MONGO_DB
    from cortex.domain.utils import _new_id

    log = _cli_log()
    container = get_container()
    repo = container.sessions
    tmux = container.terminal

    existing = repo.find_control()

    if existing:
        _status = existing["status"]
        pane_id = existing.get("pane_id")
        session_name = existing.get("name", "control")

        if _status == "active" and pane_id and tmux.pane_exists(pane_id):
            tmux.focus(pane_id)
            def _fmt_attached(d: dict) -> None:
                from cortex.cli.formatters import print_ok
                print_ok(f"Attached to {d['name']}")

            _output({"action": "attached", "session_id": existing["_id"], "name": session_name}, _fmt_attached)
            return

        if _status == "paused":
            result = subprocess.run(
                ["cortex", "--json", "session", "resume", existing["_id"]],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                click.echo(result.stdout)
                return

        if _status in ("active", "idle"):
            repo.update(existing["_id"], {"status": "closed"}, trigger="control-stale", actor="human")

    now = datetime.now()
    name = f"control-{now.strftime('%d-%b').lower()}"
    session_id = _new_id()

    repo.register(session_id, {
        "name": name, "role": "control",
        "goal": "Control session — coordinate workers, manage streams",
        "spawned_by": "cli", "workspace": "default",
        "runtime": "unknown", "color": "red",
    })

    prompt_dir = Path.home() / ".cortex" / "session-prompts"
    prompt_dir.mkdir(parents=True, exist_ok=True)
    prompt_file = prompt_dir / f"{session_id}.txt"
    prompt_file.write_text(_control_system_prompt(name, session_id))

    mongodb_uri = f"{MONGO_URI}/{MONGO_DB}"
    channels_flag = "--dangerously-load-development-channels server:cortex-team "

    cwd = os.getcwd()
    pane_id = tmux.create_interactive_pane(cwd)

    if pane_id:
        repo.update(session_id, {"pane_id": pane_id})

        env_cmd = (
            f"set -x CORTEX_SESSION_ROLE control; "
            f"set -x CORTEX_SESSION_ID {session_id}; "
            f"set -x CORTEX_SESSION_NAME {name}; "
            f"set -x CORTEX_MONGODB_URI {mongodb_uri}"
        )
        claude_cmd = (
            f"claude {channels_flag}--disallowedTools SendMessage "
            f"--name {name} --append-system-prompt-file {prompt_file}"
        )
        tmux.send_text(pane_id, env_cmd)
        time.sleep(0.3)
        tmux.send_text(pane_id, claude_cmd)

        time.sleep(1)
        tmux.send_keys(pane_id, "Enter")
        tmux.spawn_background_sender(pane_id, "/color red")
        log.info("Control session spawned", name=name, pane_id=pane_id)
    else:
        repo.update(session_id, {"status": "closed"}, trigger="spawn-fail", actor="human")
        _error_exit("Failed to launch control pane")

    data = {"action": "spawned", "session_id": session_id, "name": name, "pane_id": pane_id}

    def _fmt(d: dict) -> None:
        from cortex.cli.formatters import print_ok
        print_ok(f"Control session spawned: {d['name']} (pane {d['pane_id']})")

    _output(data, _fmt)


# ── Logs (aggregated) ───────────────────────────────────────


@click.command(cls=JsonCommand)
@click.option("-n", "--lines", default=50, help="Number of recent lines to show")
@click.option("-f", "--follow", is_flag=True, help="Follow log output (like tail -f)")
@click.option("--level", default=None, type=click.Choice(["debug", "info", "warning", "error"]), help="Filter by log level")
def logs(lines: int, follow: bool, level: str | None) -> None:
    """View aggregated logs from all Cortex components."""
    from cortex.cli.log_viewer import aggregate_tail_logs

    log_dir = CORTEX_DIR / "logs"
    if not log_dir.exists():
        _error_exit(f"No log directory at {log_dir}")

    aggregate_tail_logs(log_dir, lines=lines, follow=follow, level_filter=level)


# ── Daemon ───────────────────────────────────────────────────


@click.group(cls=JsonGroup)
def daemon() -> None:
    """Manage the Cortex background daemon."""
    pass


@daemon.command("start")
def daemon_start() -> None:
    """Start the daemon as a launchd service (auto-restarts on crash, starts on login)."""
    from cortex import daemon as daemon_mod
    try:
        daemon_mod.start()
        data = {"ok": True, "plist": str(daemon_mod.PLIST_PATH), "label": daemon_mod.PLIST_LABEL}

        def _fmt(d: dict) -> None:
            from cortex.cli.formatters import print_ok
            print_ok(f"Daemon started ({d['label']})")

        _output(data, _fmt)
    except RuntimeError as e:
        _error_exit(str(e))


@daemon.command("stop")
def daemon_stop() -> None:
    """Stop the daemon."""
    from cortex import daemon as daemon_mod
    try:
        daemon_mod.stop()
        data = {"ok": True, "stopped": daemon_mod.PLIST_LABEL}

        def _fmt(d: dict) -> None:
            from cortex.cli.formatters import print_ok
            print_ok(f"Daemon stopped ({d['stopped']})")

        _output(data, _fmt)
    except RuntimeError as e:
        _error_exit(str(e))


@daemon.command("status")
def daemon_status() -> None:
    """Check if the daemon is running."""
    from cortex import daemon as daemon_mod
    data = {"status": daemon_mod.status(), "plist": str(daemon_mod.PLIST_PATH)}

    def _fmt(d: dict) -> None:
        from cortex.cli.formatters import get_console, styled_status
        console = get_console()
        console.print(f"Daemon: {styled_status(d['status'])}")
        console.print(f"[dim]Plist: {d['plist']}[/]")

    _output(data, _fmt)


@daemon.command("run")
def daemon_run() -> None:
    """Run the daemon loop (used internally by start)."""
    from cortex.cron_executor import run
    run()


@daemon.command("logs")
@click.option("-n", "--lines", default=50, help="Number of recent lines to show")
@click.option("-f", "--follow", is_flag=True, help="Follow log output (like tail -f)")
@click.option("--level", default=None, type=click.Choice(["debug", "info", "warning", "error"]), help="Filter by log level")
@click.option("--debug", "show_debug", is_flag=True, help="Show debug log instead of info log")
def daemon_logs(lines: int, follow: bool, level: str | None, show_debug: bool) -> None:
    """View daemon logs in a human-readable format."""
    from cortex.cli.log_viewer import tail_logs

    log_name = "cortex-daemon-debug.log" if show_debug else "cortex-daemon.log"
    log_file = CORTEX_DIR / "logs" / log_name
    if not log_file.exists():
        _error_exit(f"No daemon log file at {log_file}")

    tail_logs(log_file, lines=lines, follow=follow, level_filter=level)


@daemon.command("cleanup")
@click.option("--dry-run", is_flag=True, help="Show what would be cleaned without deleting")
def daemon_cleanup(dry_run: bool) -> None:
    """Clean up stale daemon data: legacy logs, debug log bloat, orphan registry entries."""
    from pathlib import Path
    log_dir = CORTEX_DIR / "logs"

    # Legacy log files
    legacy_files = ["daemon.log", "session.log"]
    # Oversized debug logs (rotated backups from old TimedRotating config)
    # Include the current debug logs too — they're bloated from before the size cap fix
    debug_patterns = [
        "cortex-cli-debug.log", "cortex-cli-debug.log.*",
        "cortex-daemon-debug.log.*",
        "cortex-mcp-debug.log", "cortex-mcp-debug.log.*",
    ]

    cleaned_files = []
    freed_bytes = 0

    for name in legacy_files:
        path = log_dir / name
        if path.exists():
            size = path.stat().st_size
            cleaned_files.append({"file": str(path), "size_mb": round(size / 1024 / 1024, 1)})
            freed_bytes += size
            if not dry_run:
                path.unlink()

    import glob
    for pattern in debug_patterns:
        for path_str in glob.glob(str(log_dir / pattern)):
            path = Path(path_str)
            size = path.stat().st_size
            cleaned_files.append({"file": str(path), "size_mb": round(size / 1024 / 1024, 1)})
            freed_bytes += size
            if not dry_run:
                path.unlink()

    # Stale daemon entries in MongoDB
    repo = get_container().sessions
    stale = repo.list({"role": "daemon", "status": {"$in": ["active", "closed"]}})
    stale_ids = [s["_id"] for s in stale]
    if stale_ids and not dry_run:
        repo.delete_by_ids(stale_ids)

    data = {
        "dry_run": dry_run,
        "files_cleaned": cleaned_files,
        "freed_mb": round(freed_bytes / 1024 / 1024, 1),
        "stale_daemon_entries": len(stale_ids),
    }

    def _fmt(d: dict) -> None:
        from cortex.cli.formatters import get_console, print_ok
        console = get_console()
        prefix = "[dim](dry run)[/] " if d["dry_run"] else ""
        files = d.get("files_cleaned", [])
        if files:
            print_ok(f"{prefix}Cleaned {len(files)} file(s), freed {d['freed_mb']}MB")
            for f in files:
                console.print(f"  {f['file']}  [dim]({f['size_mb']}MB)[/]")
        else:
            console.print(f"{prefix}No files to clean.")
        if d["stale_daemon_entries"]:
            console.print(f"  Removed {d['stale_daemon_entries']} stale daemon entries")

    _output(data, _fmt)


# ── Errors ──────────────────────────────────────────────────


@click.group(cls=JsonGroup)
def errors() -> None:
    """Manage the error sink (dashboard error panel)."""
    pass


@errors.command("list")
@click.option("-n", "--limit", default=10, help="Number of recent errors to show")
def errors_list(limit: int) -> None:
    """List recent errors from the error sink."""
    from cortex.mongo import get_db
    db = get_db()
    docs = list(db.errors.find().sort("timestamp", -1).limit(limit))
    data = [
        {
            "id": str(d["_id"]),
            "component": d.get("component", "?"),
            "level": d.get("level", "?"),
            "event": str(d.get("event", "")),
            "timestamp": d["timestamp"].isoformat() if hasattr(d.get("timestamp"), "isoformat") else str(d.get("timestamp", "")),
        }
        for d in docs
    ]

    def _fmt(items: object) -> None:
        from cortex.cli.formatters import get_console
        console = get_console()
        if not items:
            console.print("[dim]No errors.[/]")
            return
        for item in items:  # type: ignore[union-attr]
            console.print(
                f"  [dim]{item['timestamp']}[/] [{item['level']}] "
                f"[dim]{item['component']}[/] {item['event'][:80]}"
            )

    _output(data, _fmt)


@errors.command("clear")
@click.option("--all", "clear_all", is_flag=True, help="Clear all errors (not just 24h)")
def errors_clear(clear_all: bool) -> None:
    """Clear errors from the error sink."""
    from datetime import datetime, timezone, timedelta
    from cortex.mongo import get_db
    db = get_db()

    if clear_all:
        result = db.errors.delete_many({})
    else:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        result = db.errors.delete_many({"timestamp": {"$lte": cutoff}})

    data = {"deleted": result.deleted_count, "scope": "all" if clear_all else "older_than_24h"}

    def _fmt(d: dict) -> None:
        from cortex.cli.formatters import print_ok
        print_ok(f"Cleared {d['deleted']} error(s) ({d['scope']})")

    _output(data, _fmt)


# ── Dashboard / UI ───────────────────────────────────────────


@click.command(cls=JsonCommand)
def dashboard() -> None:
    """Open the interactive TUI dashboard."""
    from cortex.tui import main as tui_main
    tui_main()


@click.command(cls=JsonCommand)
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
        webbrowser.open(f"http://localhost:{port}")
        click.echo(f"Opened http://localhost:{port}")


# ── Test ─────────────────────────────────────────────────────


SUITES = {
    "slice-0": {"marker": "slice0", "description": "Test harness self-tests"},
    "slice-1": {"marker": "slice1", "description": "Repo-based session tests"},
    "slice-2": {"marker": "slice2", "description": "Spatial spawn + layout tests"},
    "slice-3": {"marker": "slice3", "description": "Session lifecycle (pause/resume/hide/show) tests"},
    "slice-4": {"marker": "slice4", "description": "Layout control (gather/scatter/move) tests"},
}


def _preflight_checks() -> list[str]:
    import shutil
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


@click.group("test")
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
    if suite not in SUITES:
        click.echo(f"Unknown suite: {suite}\nAvailable: {', '.join(SUITES)}")
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
        click.echo(f"  [{'FAIL' if failed else 'OK'}] {label}")
    if errors:
        click.echo(f"\nPre-flight failed ({len(errors)} error(s)):")
        for e in errors:
            click.echo(f"  - {e}")
        raise SystemExit(1)

    marker = SUITES[suite]["marker"]
    cmd = ["uv", "run", "python", "-m", "pytest", "tests/e2e/", "-m", marker, "--tb=short"]
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

    smoke_checklists = {"slice-1": _smoke_slice1, "slice-2": _smoke_slice2, "slice-3": _smoke_slice3}
    if suite not in smoke_checklists:
        click.echo(f"No smoke checklist for: {suite}\nAvailable: {', '.join(smoke_checklists)}")
        raise SystemExit(1)
    checklist = smoke_checklists[suite]()
    click.echo(checklist)
    out_path = Path.home() / ".cortex" / f"smoke-test-{suite}.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(checklist)
    click.echo(f"Written to: {out_path}")


def _smoke_slice1() -> str:
    return "# Smoke Test: Slice 1\n(see cortex test smoke slice-1 for full checklist)\n"


def _smoke_slice2() -> str:
    return "# Smoke Test: Slice 2\n(see cortex test smoke slice-2 for full checklist)\n"


def _smoke_slice3() -> str:
    return "# Smoke Test: Slice 3\n(see cortex test smoke slice-3 for full checklist)\n"


# ── Deprecated team aliases ──────────────────────────────────


def _slugify(text: str) -> str:
    import re
    slug = text.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")[:50]


@click.group(hidden=True)
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
    args = ["cortex", "--json", "session", "spawn", "--name", name, "--goal", task]
    if prompt:
        args.extend(["--prompt", prompt])
    if repo:
        args.extend(["--repo", repo])
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
    args = ["cortex", "--json", "session", "message", session_name, content]
    if thread_id:
        args.extend(["--thread-id", thread_id])
    result = subprocess.run(args, capture_output=True, text=True)
    click.echo(result.stdout)


@team.command("kill")
@click.argument("session_name")
@click.pass_context
def team_kill(ctx, session_name: str) -> None:
    """[Deprecated] Use 'cortex session close --force' instead."""
    click.echo("Warning: 'cortex team kill' is deprecated. Use 'cortex session close --force' instead.", err=True)
    result = subprocess.run(["cortex", "--json", "session", "close", "--force", session_name], capture_output=True, text=True)
    click.echo(result.stdout)
