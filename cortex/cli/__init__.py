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


def _cli_log():
    return structlog.get_logger("cortex.cli")


def _json_out(data: object) -> None:
    import json
    click.echo(json.dumps(data, indent=2, default=str))


def _error_exit(msg: str) -> None:
    import json
    click.echo(json.dumps({"error": msg}))
    raise SystemExit(1)


# ── Backward-compat shim (used by stale_sweep tests) ────────


def _sweep_stale_sessions(repo) -> int:
    from datetime import datetime, timedelta, timezone

    db = repo._col.database
    messages_col = db["messages"]
    threshold = datetime.now(timezone.utc).isoformat()
    stale_cutoff = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    boot_grace = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()

    stale = list(repo._col.find({
        "status": {"$nin": ["completed", "dead"]},
        "$or": [
            {"last_seen": None, "created_at": {"$lt": boot_grace}},
            {"last_seen": {"$exists": False}, "created_at": {"$lt": boot_grace}},
            {"last_seen": {"$lt": stale_cutoff}},
        ],
    }))

    count = 0
    for s in stale:
        repo.update(s["_id"], {"status": "dead"}, trigger="stale-sweep", actor="system")
        messages_col.update_many(
            {"to": s["name"], "status": "pending"},
            {"$set": {"status": "expired", "delivered_at": threshold}},
        )
        count += 1
    return count


# Register command groups
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
