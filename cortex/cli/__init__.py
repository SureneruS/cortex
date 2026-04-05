from __future__ import annotations

import click
import structlog

from cortex.container import get_container as get_container


from cortex._version import __version__


@click.group()
@click.version_option(version=__version__, prog_name="cortex")
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


@cli.command("dashboard")
def dashboard_cmd() -> None:
    """Launch the Textual TUI dashboard."""
    from cortex.tui_dashboard import main

    main()
