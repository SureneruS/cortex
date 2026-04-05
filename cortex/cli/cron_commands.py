from __future__ import annotations

import json

import click

from cortex.cli import _error_exit, _json_out, _output


def _get_cron_mgr():
    from cortex.cron import CronManager
    from cortex.mongo import get_db

    return CronManager(get_db())


@click.group()
def cron() -> None:
    """Manage persistent cron jobs."""
    pass


def _fmt_cron_job(job: dict) -> None:
    from cortex.cli.formatters import print_detail, relative_time, styled_status, val
    fields = [
        ("Name", val(job.get("name"))),
        ("Schedule", val(job.get("cron"))),
        ("Action", val(job.get("action"))),
        ("Status", styled_status(job.get("status", "active"))),
        ("Last run", relative_time(job.get("last_run"))),
        ("Next run", val(job.get("next_run"))),
    ]
    if job.get("args"):
        fields.append(("Args", str(job["args"])))
    print_detail(fields, title=val(job.get("name"), "Cron job"))


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
    _output(job, _fmt_cron_job)


@cron.command("list")
def cron_list() -> None:
    """List all cron jobs."""
    jobs = _get_cron_mgr().list()

    def _fmt(data: list[dict]) -> None:
        from cortex.cli.formatters import print_table, relative_time, styled_status, val
        if not data:
            click.echo("No cron jobs.")
            return
        cols = [
            ("Name", {}),
            ("Schedule", {}),
            ("Action", {}),
            ("Status", {}),
            ("Last run", {"justify": "right"}),
        ]
        rows = []
        for j in data:
            rows.append([
                val(j.get("name")),
                val(j.get("cron")),
                val(j.get("action")),
                styled_status(j.get("status", "active")),
                relative_time(j.get("last_run")),
            ])
        print_table(cols, rows, count=len(data))

    _output(jobs, _fmt)


@cron.command("delete")
@click.argument("name")
def cron_delete(name: str) -> None:
    """Delete a cron job."""
    try:
        _get_cron_mgr().delete(name)
    except ValueError as e:
        _error_exit(str(e))

    def _fmt(d: dict) -> None:
        from cortex.cli.formatters import print_ok
        print_ok(f"Deleted cron job: {d['deleted']}")

    _output({"deleted": name}, _fmt)


@cron.command("pause")
@click.argument("name")
def cron_pause(name: str) -> None:
    """Pause a cron job."""
    try:
        job = _get_cron_mgr().pause(name)
    except ValueError as e:
        _error_exit(str(e))
    _output(job, _fmt_cron_job)


@cron.command("resume")
@click.argument("name")
def cron_resume(name: str) -> None:
    """Resume a paused cron job."""
    try:
        job = _get_cron_mgr().resume(name)
    except ValueError as e:
        _error_exit(str(e))
    _output(job, _fmt_cron_job)
