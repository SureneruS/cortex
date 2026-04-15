from __future__ import annotations

import json
from unittest.mock import patch

from nova.hooks.stop_failure import handle_stop_failure


def test_no_cortex_session_id_returns_empty(monkeypatch):
    monkeypatch.delenv("CORTEX_SESSION_ID", raising=False)
    result = handle_stop_failure({"error": "rate_limit"})
    assert result == {}


def _find_update_call(cli_calls):
    """Find the 'session update' call among all CLI calls."""
    for call in cli_calls:
        if len(call) >= 3 and call[0] == "session" and call[1] == "update":
            return call
    return None


def test_rate_limit_sets_error_runtime_and_notifies(monkeypatch):
    monkeypatch.setenv("CORTEX_SESSION_ID", "sess-456")
    cli_calls = []
    notify_calls = []

    def fake_cli(*args):
        cli_calls.append(args)
        return '{"name": "my-worker"}'

    def fake_notify(title, message):
        notify_calls.append((title, message))

    with patch("nova.hooks.stop_failure._cortex_cli", side_effect=fake_cli), \
         patch("nova.hooks.stop_failure._notify", side_effect=fake_notify):
        result = handle_stop_failure({
            "error": "rate_limit",
            "error_details": "Too many requests",
        })

    assert result == {}
    update_call = _find_update_call(cli_calls)
    assert update_call is not None
    data_idx = update_call.index("--data")
    data = json.loads(update_call[data_idx + 1])
    assert data["runtime"] == "error"
    assert data["last_error"]["type"] == "rate_limit"
    assert "status" not in data  # Not blocked
    assert len(notify_calls) == 1
    assert "rate_limit" in notify_calls[0][1]


def test_billing_error_blocks_session_and_escalates(monkeypatch):
    monkeypatch.setenv("CORTEX_SESSION_ID", "sess-789")
    cli_calls = []
    notify_calls = []
    human_calls = []

    def fake_cli(*args):
        cli_calls.append(args)
        return '{"name": "billing-worker"}'

    def fake_notify(title, message):
        notify_calls.append((title, message))

    def fake_human(content):
        human_calls.append(content)

    with patch("nova.hooks.stop_failure._cortex_cli", side_effect=fake_cli), \
         patch("nova.hooks.stop_failure._notify", side_effect=fake_notify), \
         patch("nova.hooks.stop_failure._send_suren_message", side_effect=fake_human):
        handle_stop_failure({"error": "billing_error", "error_details": "Payment required"})

    # Should block
    update_call = _find_update_call(cli_calls)
    assert update_call is not None
    data_idx = update_call.index("--data")
    data = json.loads(update_call[data_idx + 1])
    assert data["status"] == "blocked"
    # Should notify AND escalate to human
    assert len(notify_calls) == 1
    assert len(human_calls) == 1
    assert "billing_error" in human_calls[0]


def test_auth_error_blocks_and_escalates(monkeypatch):
    monkeypatch.setenv("CORTEX_SESSION_ID", "sess-auth")
    cli_calls = []

    def fake_cli(*args):
        cli_calls.append(args)
        return '{"name": "auth-worker"}'

    with patch("nova.hooks.stop_failure._cortex_cli", side_effect=fake_cli), \
         patch("nova.hooks.stop_failure._notify"), \
         patch("nova.hooks.stop_failure._send_suren_message"):
        handle_stop_failure({"error": "authentication_failed"})

    update_call = _find_update_call(cli_calls)
    assert update_call is not None
    data_idx = update_call.index("--data")
    data = json.loads(update_call[data_idx + 1])
    assert data["status"] == "blocked"


def test_unknown_error_sets_runtime_no_notify(monkeypatch):
    monkeypatch.setenv("CORTEX_SESSION_ID", "sess-unk")
    cli_calls = []
    notify_calls = []

    def fake_cli(*args):
        cli_calls.append(args)
        return '{"name": "unknown-worker"}'

    def fake_notify(title, message):
        notify_calls.append((title, message))

    with patch("nova.hooks.stop_failure._cortex_cli", side_effect=fake_cli), \
         patch("nova.hooks.stop_failure._notify", side_effect=fake_notify):
        handle_stop_failure({"error": "unknown"})

    update_call = _find_update_call(cli_calls)
    assert update_call is not None
    data_idx = update_call.index("--data")
    data = json.loads(update_call[data_idx + 1])
    assert data["runtime"] == "error"
    # unknown is not in NOTIFY_ERRORS or ESCALATE_ERRORS
    assert len(notify_calls) == 0


def test_error_details_truncated(monkeypatch):
    monkeypatch.setenv("CORTEX_SESSION_ID", "sess-trunc")
    cli_calls = []

    def fake_cli(*args):
        cli_calls.append(args)
        return '{"name": "trunc-worker"}'

    with patch("nova.hooks.stop_failure._cortex_cli", side_effect=fake_cli), \
         patch("nova.hooks.stop_failure._notify"), \
         patch("nova.hooks.stop_failure._send_suren_message"):
        handle_stop_failure({
            "error": "server_error",
            "error_details": "x" * 1000,
        })

    update_call = _find_update_call(cli_calls)
    assert update_call is not None
    data_idx = update_call.index("--data")
    data = json.loads(update_call[data_idx + 1])
    assert len(data["last_error"]["details"]) == 500
