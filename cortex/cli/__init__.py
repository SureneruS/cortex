from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Callable

import click
import structlog

from cortex.container import get_container as get_container


from cortex._version import __version__

if TYPE_CHECKING:
    pass


@click.group()
@click.version_option(version=__version__, prog_name="cortex")
@click.option("--json", "json_output", is_flag=True, default=False, help="Force JSON output")
@click.pass_context
def cli(ctx: click.Context, json_output: bool) -> None:
    """Cortex — persistent context brain for Claude Code."""
    from cortex.observability import bind_correlation, setup_logging

    setup_logging("cli")
    bind_correlation()
    ctx.ensure_object(dict)
    ctx.obj["json"] = json_output


def _cli_log():
    return structlog.get_logger("cortex.cli")


def _wants_json() -> bool:
    """True when output should be JSON: --json flag at any level, or stdout is not a TTY."""
    ctx = click.get_current_context(silent=True)
    while ctx:
        if ctx.params.get("json_output"):
            return True
        obj = getattr(ctx, "obj", None)
        if isinstance(obj, dict) and obj.get("json"):
            return True
        ctx = ctx.parent
    return not sys.stdout.isatty()


class JsonCommand(click.Command):
    """Command subclass that automatically adds --json flag."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.params.append(click.Option(
            ["--json"], "json_output", is_flag=True, default=False,
            expose_value=False, help="Force JSON output",
        ))


class JsonGroup(click.Group):
    """Group subclass that uses JsonCommand for all subcommands."""
    command_class = JsonCommand


def _json_out(data: object) -> None:
    import json
    click.echo(json.dumps(data, indent=2, default=str))


def _output(data: object, human_fn: Callable | None = None) -> None:
    """Output data — JSON if --json or piped, human-formatted otherwise."""
    if _wants_json() or human_fn is None:
        _json_out(data)
    else:
        human_fn(data)


def _error_exit(msg: str) -> None:
    if _wants_json():
        import json
        click.echo(json.dumps({"error": msg}))
    else:
        from cortex.cli.formatters import print_error
        print_error(msg)
    raise SystemExit(1)


# Register command groups
from cortex.cli.stream_commands import stream  # noqa: E402
from cortex.cli.session_commands import session  # noqa: E402
from cortex.cli.cron_commands import cron  # noqa: E402
from cortex.cli.pr_commands import pr  # noqa: E402
from cortex.cli.misc_commands import register_misc_commands  # noqa: E402
from cortex.cli.docs_commands import docs  # noqa: E402
from cortex.cli.knowledge_commands import dream, meditate  # noqa: E402

cli.add_command(stream)
cli.add_command(session)
cli.add_command(cron)
cli.add_command(pr)
cli.add_command(docs)
cli.add_command(dream)
cli.add_command(meditate)
register_misc_commands(cli)


@cli.command("dashboard", cls=JsonCommand)
def dashboard_cmd() -> None:
    """Launch the Textual TUI dashboard."""
    from cortex.tui_dashboard import main

    main()
