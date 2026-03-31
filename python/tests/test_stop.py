from __future__ import annotations

from unittest.mock import patch

from nova.hooks.stop import handle_stop


def test_no_cortex_session_id_returns_empty(monkeypatch):
    monkeypatch.delenv("CORTEX_SESSION_ID", raising=False)
    result = handle_stop({"last_assistant_message": "hello"})
    assert result == {}


def test_updates_runtime_and_increments_turn(monkeypatch):
    monkeypatch.setenv("CORTEX_SESSION_ID", "sess-123")
    calls = []

    def fake_cli(*args):
        calls.append(args)
        return "{}"

    with patch("nova.hooks.stop._cortex_cli", side_effect=fake_cli):
        result = handle_stop({"last_assistant_message": "I fixed the bug."})

    assert result == {}
    assert len(calls) == 1
    args = calls[0]
    assert args[0] == "session"
    assert args[1] == "update"
    assert args[2] == "sess-123"
    # Check --trigger
    trigger_idx = args.index("--trigger")
    assert args[trigger_idx + 1] == "stop_hook"
    # Check --increment
    inc_idx = args.index("--increment")
    assert args[inc_idx + 1] == "turn_count"


def test_stores_truncated_snippet(monkeypatch):
    monkeypatch.setenv("CORTEX_SESSION_ID", "sess-123")
    calls = []

    def fake_cli(*args):
        calls.append(args)
        return "{}"

    long_message = "x" * 5000

    with patch("nova.hooks.stop._cortex_cli", side_effect=fake_cli):
        handle_stop({"last_assistant_message": long_message})

    assert len(calls) == 1
    import json
    data_idx = calls[0].index("--data")
    data = json.loads(calls[0][data_idx + 1])
    assert len(data["last_response_snippet"]) == 2000


def test_empty_message_no_snippet(monkeypatch):
    monkeypatch.setenv("CORTEX_SESSION_ID", "sess-123")
    calls = []

    def fake_cli(*args):
        calls.append(args)
        return "{}"

    with patch("nova.hooks.stop._cortex_cli", side_effect=fake_cli):
        handle_stop({"last_assistant_message": ""})

    import json
    data_idx = calls[0].index("--data")
    data = json.loads(calls[0][data_idx + 1])
    assert "last_response_snippet" not in data
    assert data["runtime"] == "waiting_input"
