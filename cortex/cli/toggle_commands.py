"""Pause / resume / mode commands — toggle Cortex for vanilla CC sessions.

Pausing flips enabledPlugins["cortex@cortex"] in ~/.claude/settings.json and
stops the launchd daemon. The plugin owns all cortex hooks + the cortex-team
MCP, so disabling it leaves new CC sessions free of cortex context.

A marker file at ~/.cortex/paused records intent — lets other CLI commands
refuse operations that require the plugin (spawn, message) when we're paused.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

import click

from cortex.cli import JsonCommand, _error_exit, _output
from cortex.config import CORTEX_DIR

SETTINGS_PATH = Path.home() / ".claude" / "settings.json"
PAUSED_MARKER = CORTEX_DIR / "paused"
PLUGIN_KEY = "cortex@cortex"

_GUARDED_ACTIONS = {
    "spawn": "spawn sessions",
    "message": "send messages between sessions",
}


def is_paused() -> bool:
    # Tests set CORTEX_TESTING=1 so CLI invocations aren't blocked by the
    # user's real ~/.cortex/paused marker (which leaks into test runs).
    if os.environ.get("CORTEX_TESTING") == "1":
        return False
    return PAUSED_MARKER.exists()


def require_not_paused(action: str) -> None:
    """Called at the top of plugin-dependent commands. Bails if paused."""
    if is_paused():
        verb = _GUARDED_ACTIONS.get(action, action)
        _error_exit(
            f"Cortex is paused — cannot {verb}. "
            f"Run 'cortex resume' to re-enable the plugin and daemon."
        )


def emit_paused_banner_if_any() -> None:
    """Print a one-line banner to stderr when paused, for human CLI output."""
    if is_paused() and sys.stderr.isatty():
        click.echo(
            click.style("[cortex paused]", fg="yellow", bold=True)
            + " plugin disabled, daemon stopped — resume with 'cortex resume'",
            err=True,
        )


def _step(msg: str) -> None:
    """Emit a progress line while pause/resume work is in flight.

    Skipped in JSON mode so programmatic callers still get clean stdout.
    """
    from cortex.cli import _wants_json

    if not _wants_json():
        click.echo(f"  - {msg}")


def _read_settings() -> dict:
    if not SETTINGS_PATH.exists():
        _error_exit(f"Claude Code settings not found at {SETTINGS_PATH}")
    try:
        return json.loads(SETTINGS_PATH.read_text())
    except json.JSONDecodeError as e:
        _error_exit(f"Could not parse {SETTINGS_PATH}: {e}")


def _write_settings(data: dict) -> None:
    SETTINGS_PATH.write_text(json.dumps(data, indent=2) + "\n")


def _set_plugin_enabled(enabled: bool) -> bool:
    """Flip enabledPlugins[cortex@cortex]. Returns True if value changed."""
    data = _read_settings()
    plugins = data.setdefault("enabledPlugins", {})
    if plugins.get(PLUGIN_KEY) == enabled:
        return False
    plugins[PLUGIN_KEY] = enabled
    _write_settings(data)
    return True


def _plugin_enabled() -> bool | None:
    data = _read_settings()
    return data.get("enabledPlugins", {}).get(PLUGIN_KEY)


def _active_sessions() -> list[dict]:
    from cortex.container import get_container
    sessions = get_container().sessions.list({"status": {"$in": ["active", "idle"]}})
    return [s for s in sessions if s.get("role") != "daemon"]


@click.command(cls=JsonCommand)
@click.option("--force", is_flag=True, help="Skip the active-session confirmation prompt")
def pause(force: bool) -> None:
    """Disable the Cortex plugin and stop the daemon for vanilla CC mode."""
    if is_paused():
        _error_exit("Cortex is already paused.")

    _step("Checking active sessions...")
    active = _active_sessions()
    if active and not force:
        click.echo(f"Warning: {len(active)} active session(s):")
        for s in active[:5]:
            click.echo(f"  - {s.get('name', s['_id'])}  [{s.get('status')}]")
        if len(active) > 5:
            click.echo(f"  ...and {len(active) - 5} more")
        click.echo(
            "\nThese keep cortex features (plugin already loaded in their CC process).\n"
            "New CC sessions will not have cortex features until resumed.\n"
        )
        if not click.confirm("Continue pausing?", default=False):
            raise SystemExit(0)

    _step("Disabling cortex@cortex plugin in ~/.claude/settings.json...")
    plugin_changed = _set_plugin_enabled(False)

    _step("Stopping launchd daemon...")
    from cortex import daemon as daemon_mod
    try:
        daemon_mod.stop()
        daemon_stopped = True
    except RuntimeError:
        daemon_stopped = False

    _step("Writing pause marker...")
    PAUSED_MARKER.parent.mkdir(parents=True, exist_ok=True)
    PAUSED_MARKER.write_text(
        json.dumps({"paused_at": datetime.now().isoformat()}, indent=2) + "\n"
    )

    data = {
        "paused": True,
        "plugin_was_enabled": plugin_changed,
        "daemon_stopped": daemon_stopped,
        "active_sessions_kept": len(active),
    }

    def _fmt(d: dict) -> None:
        from cortex.cli.formatters import print_ok
        print_ok("Cortex paused")
        click.echo(f"  - Plugin cortex@cortex disabled in {SETTINGS_PATH}")
        click.echo(
            "  - Daemon "
            + ("stopped" if d["daemon_stopped"] else "(was not running)")
        )
        if d["active_sessions_kept"]:
            click.echo(
                f"  - {d['active_sessions_kept']} existing session(s) keep cortex until they exit"
            )
        click.echo("\nStart a fresh CC session to see vanilla mode. Resume with 'cortex resume'.")

    _output(data, _fmt)


@click.command(cls=JsonCommand)
def resume() -> None:
    """Re-enable the Cortex plugin and start the daemon."""
    if not is_paused():
        _error_exit("Cortex is not paused.")

    _step("Enabling cortex@cortex plugin in ~/.claude/settings.json...")
    plugin_changed = _set_plugin_enabled(True)

    _step("Starting launchd daemon...")
    from cortex import daemon as daemon_mod
    try:
        daemon_mod.start()
        daemon_started = True
        daemon_error: str | None = None
    except RuntimeError as e:
        daemon_started = False
        daemon_error = str(e)

    _step("Removing pause marker...")
    PAUSED_MARKER.unlink(missing_ok=True)

    data = {
        "paused": False,
        "plugin_was_disabled": plugin_changed,
        "daemon_started": daemon_started,
        "daemon_error": daemon_error,
    }

    def _fmt(d: dict) -> None:
        from cortex.cli.formatters import print_ok
        print_ok("Cortex resumed")
        click.echo(f"  - Plugin cortex@cortex enabled in {SETTINGS_PATH}")
        if d["daemon_started"]:
            click.echo("  - Daemon started")
        else:
            click.echo(f"  - Daemon FAILED to start: {d['daemon_error']}")
            click.echo("    Check 'cortex daemon status' and retry 'cortex daemon start'.")
        click.echo("\nStart a fresh CC session to apply.")

    _output(data, _fmt)


@click.command("mode", cls=JsonCommand)
def mode_cmd() -> None:
    """Show whether Cortex is currently active or paused."""
    from cortex import daemon as daemon_mod

    paused = is_paused()
    plugin = _plugin_enabled()
    daemon_state = daemon_mod.status()
    marker_info: dict | None = None
    if paused:
        try:
            marker_info = json.loads(PAUSED_MARKER.read_text())
        except (OSError, json.JSONDecodeError):
            marker_info = None

    data = {
        "mode": "paused" if paused else "active",
        "plugin_enabled": plugin,
        "daemon_status": daemon_state,
        "paused_at": marker_info.get("paused_at") if marker_info else None,
    }

    def _fmt(d: dict) -> None:
        from cortex.cli.formatters import get_console, styled_status
        console = get_console()
        label = "PAUSED" if d["mode"] == "paused" else "ACTIVE"
        color = "yellow" if d["mode"] == "paused" else "green"
        console.print(f"Mode: [{color} bold]{label}[/]")
        console.print(f"  Plugin cortex@cortex: {d['plugin_enabled']!r}")
        console.print(f"  Daemon: {styled_status(d['daemon_status'])}")
        if d.get("paused_at"):
            console.print(f"  Paused at: {d['paused_at']}")

    _output(data, _fmt)
