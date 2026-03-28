from __future__ import annotations

import json

import click

from cortex.cli import _error_exit, _json_out


def _get_cron_mgr():
    from cortex.cron import CronManager
    from cortex.mongo import get_db

    return CronManager(get_db())


@click.group()
def cron() -> None:
    """Manage persistent cron jobs."""
    pass


@cron.command("create")
@click.option("--name", required=True, help="Unique job name")
@click.option("--cron", "cron_expr", required=True, help="5-field cron expression")
@click.option("--action", required=True, help="Action type (check-watches, command)")
@click.option("--args", "action_args", default=None, help="JSON action args")
def cron_create(name: str, cron_expr: str, action: str, action_args: str | None) -> None:
    """Create a cron job."""
    parsed_args = None
    if action_args:
        try:
            parsed_args = json.loads(action_args)
        except json.JSONDecodeError as e:
            _error_exit(f"Invalid JSON in --args: {e}")

    mgr = _get_cron_mgr()
    try:
        job = mgr.create(name, cron_expr, action, parsed_args)
    except ValueError as e:
        _error_exit(str(e))
    _json_out(job)


@cron.command("list")
def cron_list() -> None:
    """List all cron jobs."""
    _json_out(_get_cron_mgr().list())


@cron.command("delete")
@click.argument("name")
def cron_delete(name: str) -> None:
    """Delete a cron job."""
    try:
        _get_cron_mgr().delete(name)
    except ValueError as e:
        _error_exit(str(e))
    _json_out({"deleted": name})


@cron.command("pause")
@click.argument("name")
def cron_pause(name: str) -> None:
    """Pause a cron job."""
    try:
        job = _get_cron_mgr().pause(name)
    except ValueError as e:
        _error_exit(str(e))
    _json_out(job)


@cron.command("resume")
@click.argument("name")
def cron_resume(name: str) -> None:
    """Resume a paused cron job."""
    try:
        job = _get_cron_mgr().resume(name)
    except ValueError as e:
        _error_exit(str(e))
    _json_out(job)
