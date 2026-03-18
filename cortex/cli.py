from __future__ import annotations

import click

from cortex.config import CORTEX_DIR, load_config, save_config, Config
from cortex.state import StateManager


@click.group()
def cli() -> None:
    """Cortex — persistent context brain for Claude Code."""
    pass


@cli.command()
def init() -> None:
    """Initialize Cortex: create config, DB, and scan repos for context."""
    click.echo("Initializing Cortex...")

    config = Config()
    save_config(config)
    click.echo(f"  Config saved to {CORTEX_DIR / 'config.json'}")

    state = StateManager(config.resolved_db_path)
    state.init_db()
    click.echo(f"  Database initialized at {config.resolved_db_path}")

    click.echo("  Scanning repos for open PRs...")
    from cortex.bootstrap import scan_repos

    stats = scan_repos(config, state)

    click.echo("\nBootstrap complete:")
    click.echo(f"  Repos scanned: {stats['repos_scanned']}")
    click.echo(f"  Open PRs found: {stats['prs_found']}")
    click.echo(f"  Active branches: {stats['branches_found']}")
    click.echo(f"  Streams created: {stats['streams_created']}")

    state.close()


@cli.command()
def status() -> None:
    """Show active Cortex streams."""
    config = load_config()
    state = StateManager(config.resolved_db_path)
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
    state = StateManager(config.resolved_db_path)
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
    state = StateManager(config.resolved_db_path)
    state.init_db()
    state.link_session(session_id, stream_id)
    state.close()


@cli.command()
@click.option("--session-id", default=None, help="Claude Code session ID to restore tasks for.")
def tasks(session_id: str | None) -> None:
    """Print pending task backups for session restore."""
    config = load_config()
    state = StateManager(config.resolved_db_path)
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
    """Rebuild search indexes (FTS + vector embeddings)."""
    config = load_config()
    state = StateManager(config.resolved_db_path)
    state.init_db()

    click.echo("Clearing existing indexes...")
    state.clear_indexes()

    click.echo("Rebuilding FTS index...")
    state._rebuild_search_index()

    click.echo("Rebuilding vector index...")
    state._rebuild_vec_index()

    click.echo("Done.")
    state.close()


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


def _cli_log():
    import logging
    from pathlib import Path

    log = logging.getLogger("cortex.session.cli")
    if not log.handlers:
        log.setLevel(logging.DEBUG)
        log_dir = Path.home() / ".cortex" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_dir / "session.log")
        fh.setFormatter(
            logging.Formatter(
                "[%(asctime)s] %(name)s %(levelname)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
            )
        )
        log.addHandler(fh)
    return log


@session.command()
@click.option("--name", required=True, help="Session name")
@click.option("--goal", default=None, help="Registry metadata describing the session's purpose")
@click.option("--prompt", default=None, help="Prompt to send to the session after it starts")
@click.option("--workspace", default="default", help="Workspace (default or background)")
@click.option("--model", default=None, help="Claude model (e.g. haiku, sonnet, opus)")
@click.option("--split", is_flag=True, default=False, help="Split current pane horizontally instead of new tab")
@click.option("--resume", "resume_id", default=None, help="CC session UUID to resume (continues previous conversation)")
def spawn(name: str, goal: str | None, prompt: str | None, workspace: str, model: str | None, split: bool, resume_id: str | None) -> None:
    """Spawn a new Claude Code session in a tmux pane."""
    import json
    import subprocess

    from cortex.session_registry import _new_id

    log = _cli_log()
    log.info("CLI spawn called: name=%s goal=%s prompt=%s workspace=%s resume=%s", name, goal, bool(prompt), workspace, resume_id)

    repo = _get_session_repo()
    session_id = _new_id()
    log.info("Generated session_id: %s", session_id)

    data = {
        "name": name,
        "workspace": workspace,
        "spawned_by": "control",
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

    repo.register(session_id, data)
    log.info("Session registered in MongoDB")

    system_prompt = (
        f"You are a worker session (ID: {session_id}, name: {name})."
        f" Focus on your assigned task. Self-update your status via cortex session update."
    )

    from pathlib import Path

    prompt_dir = Path.home() / ".cortex" / "session-prompts"
    prompt_dir.mkdir(parents=True, exist_ok=True)
    prompt_file = prompt_dir / f"{session_id}.txt"
    prompt_file.write_text(system_prompt)
    log.info("Wrote system prompt to %s", prompt_file)

    model_flag = f"--model {model} " if model else ""
    resume_flag = f"--resume {resume_id} " if resume_id else ""
    fish_cmd = (
        f"set -x CORTEX_SESSION_ROLE worker; "
        f"set -x CORTEX_SESSION_ID {session_id}; "
        f"claude {model_flag}{resume_flag}--name {name} --append-system-prompt-file {prompt_file}; exit"
    )

    import os

    spawn_mode = "split" if split else os.environ.get("CORTEX_SPAWN_MODE", "tab")
    cwd = os.getcwd()
    log.info("Spawn cwd: %s spawn_mode: %s", cwd, spawn_mode)

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
    elif spawn_mode == "split":
        caller_pane = _resolve_caller_pane(repo)
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
        repo.update(session_id, {"pane_id": pane_id})
        log.info("Updated session with pane_id=%s", pane_id)

        if prompt:
            prompt_file_path = prompt_dir / f"{session_id}-prompt.txt"
            prompt_file_path.write_text(prompt)
            log_file = Path.home() / ".cortex" / "logs" / "prompt-sender.log"
            send_script = (
                f"set log_file {log_file}; "
                f"echo (date) 'Prompt sender started for pane {pane_id}' >> $log_file; "
                f"set attempt 0; "
                f"while not tmux capture-pane -t {pane_id} -p 2>/dev/null | grep -q '❯'; "
                f"set attempt (math $attempt + 1); "
                f'echo (date) "Attempt $attempt: waiting for prompt on pane {pane_id}" >> $log_file; '
                f"if test $attempt -gt 30; echo (date) 'Timed out after 30 attempts' >> $log_file; exit 1; end; "
                f"sleep 1; end; "
                f"echo (date) 'Prompt detected, sending to pane {pane_id}' >> $log_file; "
                f"tmux send-keys -t {pane_id} -l (cat {prompt_file_path}); "
                f"sleep 0.5; "
                f"tmux send-keys -t {pane_id} Enter; "
                f"echo (date) 'Prompt sent successfully to pane {pane_id}' >> $log_file"
            )
            subprocess.Popen(
                ["fish", "-c", send_script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            log.info("Launched background prompt sender for pane %s (log: %s)", pane_id, log_file)
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
    """List registered sessions."""
    import json

    repo = _get_session_repo()
    filters = {}
    if filter_status:
        filters["status"] = filter_status
    if filter_runtime:
        filters["runtime"] = filter_runtime
    sessions = repo.list(filters, brief=brief, limit=limit)
    click.echo(json.dumps(sessions, indent=2, default=str))


@session.command()
@click.argument("session_id")
def get(session_id: str) -> None:
    """Get a session by ID."""
    import json

    repo = _get_session_repo()
    doc = repo.get(session_id)
    if doc is None:
        click.echo(json.dumps({"error": f"Session {session_id} not found"}))
        raise SystemExit(1)
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
    try:
        doc = repo.update(session_id, fields, trigger=trigger)
    except ValueError as e:
        log.error("Validation error: %s", e)
        click.echo(json.dumps({"error": str(e)}))
        raise SystemExit(1)

    if doc is None:
        log.warning("Session not found: %s", session_id)
        click.echo(json.dumps({"error": f"Session {session_id} not found"}))
        raise SystemExit(1)

    log.info("CLI session update complete: %s", session_id)
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
    import subprocess

    if "\n" in text or len(text) > 200:
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write(text)
            tmp_path = f.name
        subprocess.run(
            ["tmux", "load-buffer", tmp_path],
            capture_output=True,
            text=True,
        )
        result = subprocess.run(
            ["tmux", "paste-buffer", "-t", pane_id],
            capture_output=True,
            text=True,
        )
    else:
        result = subprocess.run(
            ["tmux", "send-keys", "-t", pane_id, "-l", text],
            capture_output=True,
            text=True,
        )
    if result.returncode != 0:
        return False
    result = subprocess.run(
        ["tmux", "send-keys", "-t", pane_id, "Enter"],
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
        last_line = result.stdout.rstrip().rsplit("\n", 1)[-1]
        if "❯" in last_line:
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
@click.argument("session_id")
@click.argument("text")
def send(session_id: str, text: str) -> None:
    """Send text to a session's tmux pane (and press Enter)."""
    import json

    log = _cli_log()
    repo = _get_session_repo()
    doc = repo.get(session_id)
    if doc is None:
        click.echo(json.dumps({"error": f"Session {session_id} not found"}))
        raise SystemExit(1)

    pane_id = doc.get("pane_id")
    if pane_id is None or not _pane_exists(pane_id):
        click.echo(json.dumps({"error": f"Pane not available for session {session_id}"}))
        raise SystemExit(1)

    ok = _send_to_pane(pane_id, text)
    log.info("Send to session %s pane %s: ok=%s text=%r", session_id, pane_id, ok, text[:100])
    click.echo(json.dumps({"ok": ok, "session_id": session_id, "pane_id": pane_id}))


@session.command()
@click.argument("session_id")
@click.option("--lines", default=50, help="Number of scrollback lines to capture")
def capture(session_id: str, lines: int) -> None:
    """Capture terminal output from a session's tmux pane."""
    import json
    import subprocess

    log = _cli_log()
    repo = _get_session_repo()
    doc = repo.get(session_id)
    if doc is None:
        click.echo(json.dumps({"error": f"Session {session_id} not found"}))
        raise SystemExit(1)

    pane_id = doc.get("pane_id")
    if pane_id is None or not _pane_exists(pane_id):
        click.echo(json.dumps({"error": f"Pane not available for session {session_id}"}))
        raise SystemExit(1)

    result = subprocess.run(
        ["tmux", "capture-pane", "-t", pane_id, "-p", "-S", str(-lines)],
        capture_output=True,
        text=True,
    )
    output = result.stdout.rstrip() if result.returncode == 0 else ""
    log.info("Capture session %s pane %s: %d chars", session_id, pane_id, len(output))
    click.echo(json.dumps({"session_id": session_id, "pane_id": pane_id, "output": output}))


@session.command()
@click.argument("session_id")
@click.option("--force", is_flag=True, help="Skip /memorize and close immediately")
def close(session_id: str, force: bool) -> None:
    """Close a session with full wrapup lifecycle.

    Steps: send /memorize, wait for completion, update linked stream, close registry, kill/exit pane.
    Use --force to skip /memorize and close immediately.
    """
    import json
    import os

    log = _cli_log()
    log.info("CLI session close called: session_id=%s force=%s", session_id, force)

    repo = _get_session_repo()
    doc = repo.get(session_id)
    if doc is None:
        log.warning("Session not found: %s", session_id)
        click.echo(json.dumps({"error": f"Session {session_id} not found"}))
        raise SystemExit(1)

    pane_id = doc.get("pane_id")
    self_close = os.environ.get("CORTEX_SESSION_ID") == session_id
    pane_alive = pane_id is not None and _pane_exists(pane_id)
    log.info("pane_id=%s pane_alive=%s", pane_id, pane_alive)

    # Step 1: Send /memorize (unless --force or pane gone)
    memorize_ok = False
    if not force and pane_alive:
        log.info("Sending /memorize to pane %s", pane_id)
        if _send_to_pane(pane_id, "/memorize"):
            log.info("Waiting for /memorize to complete (timeout=30s)")
            memorize_ok = _wait_for_idle(pane_id, timeout=30)
            if memorize_ok:
                log.info("/memorize completed on pane %s", pane_id)
            else:
                log.warning("/memorize timed out on pane %s, continuing with close", pane_id)
        else:
            log.warning("Failed to send /memorize to pane %s", pane_id)
    elif force:
        log.info("Skipping /memorize (--force)")
    else:
        log.info("Skipping /memorize (pane not available)")

    # Step 2: Update linked Cortex stream (if any)
    config = load_config()
    state = StateManager(config.resolved_db_path)
    state.init_db()
    stream_ids = state.get_streams_for_session(session_id)
    if stream_ids:
        log.info("Linked streams: %s", stream_ids)
        for sid in stream_ids:
            state.add_update(
                sid,
                f"Session {doc.get('name', session_id)} closed.",
                f"Session closed (memorize={'ok' if memorize_ok else 'skipped'})",
                metadata={"type": "session_close", "session_id": session_id},
            )
            log.info("Logged close update to stream %s", sid)
    state.close()

    # Step 3: Close registry entry
    doc = repo.close(session_id)
    log.info("Registry entry closed: status=%s", doc["status"])

    # Step 4: Terminate tmux pane
    if pane_alive:
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
        last_line = result.stdout.rstrip().rsplit("\n", 1)[-1] if result.stdout else ""
        if "❯" in last_line:
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


if __name__ == "__main__":
    cli()
