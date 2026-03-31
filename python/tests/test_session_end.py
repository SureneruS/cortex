from __future__ import annotations

import json
from unittest.mock import patch

from nova.hooks.session_end import handle_session_end


def test_no_cortex_session_id_returns_empty(monkeypatch):
    monkeypatch.delenv("CORTEX_SESSION_ID", raising=False)
    result = handle_session_end({"reason": "exit"})
    assert result == {}


def test_exit_marks_completed(monkeypatch):
    monkeypatch.setenv("CORTEX_SESSION_ID", "sess-end-1")
    cli_calls = []

    def fake_cli(*args):
        cli_calls.append(args)
        return '{"name": "worker-1"}'

    with patch("nova.hooks.session_end._cortex_cli", side_effect=fake_cli), \
         patch("nova.hooks.session_end._notify"):
        result = handle_session_end({"reason": "exit"})

    assert result == {}
    # First call is session_name lookup, second is the update
    update_call = [c for c in cli_calls if "update" in c][0]
    data_idx = update_call.index("--data")
    data = json.loads(update_call[data_idx + 1])
    assert data["status"] == "completed"
    assert "ended_at" in data
    assert data["end_reason"] == "exit"
    trigger_idx = update_call.index("--trigger")
    assert update_call[trigger_idx + 1] == "session_end_exit"


def test_clear_keeps_active(monkeypatch):
    monkeypatch.setenv("CORTEX_SESSION_ID", "sess-clear-1")
    cli_calls = []

    def fake_cli(*args):
        cli_calls.append(args)
        return '{"name": "worker-clear"}'

    with patch("nova.hooks.session_end._cortex_cli", side_effect=fake_cli), \
         patch("nova.hooks.session_end._notify"):
        result = handle_session_end({"reason": "clear"})

    assert result == {}
    update_call = [c for c in cli_calls if "update" in c][0]
    data_idx = update_call.index("--data")
    data = json.loads(update_call[data_idx + 1])
    # Should NOT set status to completed
    assert "status" not in data
    assert data["last_session_end"]["reason"] == "clear"


def test_resume_keeps_active(monkeypatch):
    monkeypatch.setenv("CORTEX_SESSION_ID", "sess-resume-1")
    cli_calls = []

    def fake_cli(*args):
        cli_calls.append(args)
        return '{"name": "worker-resume"}'

    with patch("nova.hooks.session_end._cortex_cli", side_effect=fake_cli), \
         patch("nova.hooks.session_end._notify"):
        result = handle_session_end({"reason": "resume"})

    assert result == {}
    update_call = [c for c in cli_calls if "update" in c][0]
    data_idx = update_call.index("--data")
    data = json.loads(update_call[data_idx + 1])
    assert "status" not in data


def test_logout_marks_completed(monkeypatch):
    monkeypatch.setenv("CORTEX_SESSION_ID", "sess-logout-1")
    cli_calls = []

    def fake_cli(*args):
        cli_calls.append(args)
        return '{"name": "worker-logout"}'

    with patch("nova.hooks.session_end._cortex_cli", side_effect=fake_cli), \
         patch("nova.hooks.session_end._notify"):
        handle_session_end({"reason": "logout"})

    update_call = [c for c in cli_calls if "update" in c][0]
    data_idx = update_call.index("--data")
    data = json.loads(update_call[data_idx + 1])
    assert data["status"] == "completed"


def test_prompt_input_exit_marks_completed(monkeypatch):
    monkeypatch.setenv("CORTEX_SESSION_ID", "sess-pie-1")
    cli_calls = []

    def fake_cli(*args):
        cli_calls.append(args)
        return '{"name": "worker-pie"}'

    with patch("nova.hooks.session_end._cortex_cli", side_effect=fake_cli), \
         patch("nova.hooks.session_end._notify"):
        handle_session_end({"reason": "prompt_input_exit"})

    update_call = [c for c in cli_calls if "update" in c][0]
    data_idx = update_call.index("--data")
    data = json.loads(update_call[data_idx + 1])
    assert data["status"] == "completed"


def test_notifies_on_terminal_reasons(monkeypatch):
    monkeypatch.setenv("CORTEX_SESSION_ID", "sess-notify-1")
    notify_calls = []

    def fake_cli(*args):
        return '{"name": "my-session"}'

    def fake_notify(subtitle, message):
        notify_calls.append((subtitle, message))

    with patch("nova.hooks.session_end._cortex_cli", side_effect=fake_cli), \
         patch("nova.hooks.session_end._notify", side_effect=fake_notify):
        handle_session_end({"reason": "exit"})

    assert len(notify_calls) == 1
    assert "my-session" in notify_calls[0][1]


def test_notifies_on_clear(monkeypatch):
    monkeypatch.setenv("CORTEX_SESSION_ID", "sess-clear-notify")
    notify_calls = []

    def fake_cli(*args):
        return '{"name": "clear-session"}'

    def fake_notify(subtitle, message):
        notify_calls.append((subtitle, message))

    with patch("nova.hooks.session_end._cortex_cli", side_effect=fake_cli), \
         patch("nova.hooks.session_end._notify", side_effect=fake_notify):
        handle_session_end({"reason": "clear"})

    assert len(notify_calls) == 1
    assert notify_calls[0][1] == "Session cleared"


def test_unknown_reason_defaults_to_completed(monkeypatch):
    monkeypatch.setenv("CORTEX_SESSION_ID", "sess-other")
    cli_calls = []

    def fake_cli(*args):
        cli_calls.append(args)
        return '{"name": "other-session"}'

    with patch("nova.hooks.session_end._cortex_cli", side_effect=fake_cli), \
         patch("nova.hooks.session_end._notify"):
        handle_session_end({"reason": "other"})

    update_call = [c for c in cli_calls if "update" in c][0]
    data_idx = update_call.index("--data")
    data = json.loads(update_call[data_idx + 1])
    assert data["status"] == "completed"
