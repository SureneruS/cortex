from __future__ import annotations

import click
import structlog

from cortex.config import load_config, Config, CONFIG_PATH, CORTEX_DIR, save_config
from cortex.container import get_container
from cortex.mongo import get_db
from cortex.mongo_state import MongoStateManager


@click.group()
def cli() -> None:
    """Cortex — persistent context brain for Claude Code."""
    from cortex.observability import bind_correlation, setup_logging

    setup_logging("cli")
    bind_correlation()


def _get_state() -> MongoStateManager:
    config = load_config()
    sm = MongoStateManager(get_db(), config.resolved_vec_db_path)
    sm.init_db()
    return sm


def _cli_log():
    return structlog.get_logger("cortex.cli")


def _json_out(data: object) -> None:
    import json
    click.echo(json.dumps(data, indent=2, default=str))


def _error_exit(msg: str) -> None:
    import json
    click.echo(json.dumps({"error": msg}))
    raise SystemExit(1)


# ── Backward-compatible shims for test mocking ───────────────
# Tests patch cortex.cli._pane_exists etc. These delegate to the adapter.


def _pane_exists(pane_id: str | int) -> bool:
    return get_container().terminal.pane_exists(str(pane_id))


def _send_to_pane(pane_id: str | int, text: str) -> bool:
    return get_container().terminal.send_text(str(pane_id), text)


def _wait_for_idle(pane_id: str | int, timeout: int = 30) -> bool:
    return get_container().terminal.wait_for_idle(str(pane_id), timeout)


def _kill_pane(pane_id: str | int) -> bool:
    return get_container().terminal.destroy_pane(str(pane_id))


def _get_tmux_panes() -> set[str]:
    return get_container().terminal.list_pane_ids()


def _sweep_stale_sessions(repo) -> int:
    """Backward-compat shim for tests — delegates to service layer logic."""
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


# Register command groups — import triggers Click decorator registration
from cortex.cli.stream_commands import stream  # noqa: E402
from cortex.cli.session_commands import session  # noqa: E402
from cortex.cli.cron_commands import cron  # noqa: E402
from cortex.cli.pr_commands import pr  # noqa: E402
from cortex.cli.misc_commands import register_misc_commands  # noqa: E402

cli.add_command(stream)
cli.add_command(session)
cli.add_command(cron)
cli.add_command(pr)
register_misc_commands(cli)
