from __future__ import annotations

from io import StringIO

from rich.console import Console

from cortex.tui_dashboard import _render_spawn_card, _render_event_line


def _render_to_text(renderable, width: int = 80) -> str:
    console = Console(file=StringIO(), width=width, no_color=True, legacy_windows=False)
    console.print(renderable, end="")
    return console.file.getvalue()


def test_spawn_card_shows_all_params():
    ev = {
        "session_name": "dashboard-spawn-params",
        "trigger": "spawn",
        "actor": "control-15-apr",
        "at": "2026-04-15T05:51:03+00:00",
        "session_role": "worker",
        "session_workspace": "default",
        "session_color": "cyan",
        "session_repos": ["cortex"],
        "session_worktree": "ats-831",
        "session_channel_status": "ready",
    }
    out = _render_to_text(_render_spawn_card(ev))
    assert "spawned" in out
    assert "dashboard-spawn-params" in out
    assert "worker" in out
    assert "control-15-apr" in out
    assert "default" in out
    assert "cortex" in out
    assert "cyan" in out
    assert "ats-831" in out
    assert " on" in out  # channels on


def test_spawn_card_missing_fields_renders_em_dash():
    ev = {
        "session_name": "minimal",
        "trigger": "spawn",
        "actor": "cli",
        "at": "2026-04-15T05:51:03+00:00",
    }
    out = _render_to_text(_render_spawn_card(ev))
    assert "minimal" in out
    assert "—" in out  # missing fields shown as em-dash
    assert "off" in out  # channels off when channel_status missing


def test_spawn_card_channels_off_when_missing_status():
    ev = {
        "session_name": "no-chan",
        "trigger": "spawn",
        "actor": "cli",
        "at": "2026-04-15T05:51:03+00:00",
        "session_channel_status": None,
    }
    out = _render_to_text(_render_spawn_card(ev))
    assert "off" in out


def test_event_line_still_renders_non_spawn():
    ev = {
        "session_name": "foo",
        "trigger": "hide",
        "from": "active",
        "to": "hidden",
        "at": "2026-04-15T05:51:03+00:00",
    }
    out = _render_to_text(_render_event_line(ev))
    assert "foo" in out
    assert "active" in out
    assert "hidden" in out
