"""Convenience commands for dream and meditate workflows."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import click

from cortex.cli import JsonCommand, _cli_log, _error_exit, _output, get_container
from cortex.services.session_service import SpawnDenied


CORTEX_REPO = Path.home() / "workspace" / "cercli" / "cortex"

DREAM_PROMPT = (
    "Process all captures in ~/cortex/captures/. Follow your dream workflow. "
    "When done, run /session-wrapup and /exit."
)


@click.command(cls=JsonCommand)
def dream() -> None:
    """Spawn a dream session to consolidate captures into knowledge files."""
    log = _cli_log()
    name = f"dream-{datetime.now().strftime('%d-%b').lower()}"
    svc = get_container().session_service

    try:
        result = svc.spawn(
            name=name,
            goal="Dream: consolidate captures into knowledge files",
            prompt=DREAM_PROMPT,
            workspace="default",
            repo_path=CORTEX_REPO,
            agent_name="dream",
        )
    except (ValueError, SpawnDenied) as e:
        _error_exit(str(e))

    log.info("Dream session spawned", name=name)

    def _fmt(data: dict) -> None:
        from cortex.cli.formatters import print_ok
        print_ok(f"Dream session spawned: {data['name']} (pane {data.get('pane_id', '?')})")

    _output(result, _fmt)


@click.command(cls=JsonCommand)
def meditate() -> None:
    """Spawn an interactive meditate session to promote knowledge into rules."""
    log = _cli_log()
    name = f"meditate-{datetime.now().strftime('%d-%b').lower()}"
    svc = get_container().session_service

    try:
        result = svc.spawn(
            name=name,
            goal="Meditate: promote knowledge files into CLAUDE.md and rules",
            workspace="default",
            repo_path=CORTEX_REPO,
            agent_name="meditate",
        )
    except (ValueError, SpawnDenied) as e:
        _error_exit(str(e))

    log.info("Meditate session spawned", name=name)

    def _fmt(data: dict) -> None:
        from cortex.cli.formatters import print_ok
        print_ok(f"Meditate session spawned: {data['name']} (pane {data.get('pane_id', '?')})")

    _output(result, _fmt)
