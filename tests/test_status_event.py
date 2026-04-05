"""Tests for status_event.py — channel emission + registry runtime updates."""

from __future__ import annotations

import json
from unittest.mock import patch, call, MagicMock

import pytest

from nova.hooks.status_event import emit_status_event, _EVENT_TO_RUNTIME


@pytest.fixture(autouse=True)
def _set_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CORTEX_SESSION_NAME", "worker-1")
    monkeypatch.setenv("CORTEX_PARENT_NAME", "control-main")
    monkeypatch.setenv("CORTEX_SESSION_ID", "sess-abc-123")


class TestRegistryUpdate:
    """Status events with a runtime mapping should call cortex session update."""

    @pytest.mark.parametrize("event,expected_runtime", list(_EVENT_TO_RUNTIME.items()))
    def test_mapped_events_update_registry(self, event: str, expected_runtime: str):
        with patch("nova.hooks.status_event.subprocess.Popen") as mock_popen:
            emit_status_event(event, "some detail")

        # Two Popen calls: one for registry update, one for channel message
        assert mock_popen.call_count == 2
        update_call = mock_popen.call_args_list[0]
        cmd = update_call[0][0]
        assert cmd[:4] == ["cortex", "--json", "session", "update"]
        assert "sess-abc-123" in cmd
        data_idx = cmd.index("--data") + 1
        assert json.loads(cmd[data_idx]) == {"runtime": expected_runtime}
        assert "--trigger" in cmd
        assert "status-event" in cmd

    def test_done_event_skips_registry_update(self):
        with patch("nova.hooks.status_event.subprocess.Popen") as mock_popen:
            emit_status_event("done", "Session ended")

        # Only the channel message, no registry update
        assert mock_popen.call_count == 1
        cmd = mock_popen.call_args_list[0][0][0]
        assert "message" in cmd

    def test_unknown_event_skips_registry_update(self):
        with patch("nova.hooks.status_event.subprocess.Popen") as mock_popen:
            emit_status_event("some_unknown_event")

        assert mock_popen.call_count == 1


class TestChannelMessage:
    """Channel message to parent should always be sent."""

    def test_channel_message_sent(self):
        with patch("nova.hooks.status_event.subprocess.Popen") as mock_popen:
            emit_status_event("started", "Session started in cortex")

        message_call = mock_popen.call_args_list[-1]
        cmd = message_call[0][0]
        assert cmd[:4] == ["cortex", "--json", "session", "message"]
        assert "control-main" in cmd


class TestNoOps:
    """Should no-op when required env vars are missing."""

    def test_no_session_name(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("CORTEX_SESSION_NAME")
        with patch("nova.hooks.status_event.subprocess.Popen") as mock_popen:
            emit_status_event("started")
        mock_popen.assert_not_called()

    def test_no_parent_name(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("CORTEX_PARENT_NAME")
        with patch("nova.hooks.status_event.subprocess.Popen") as mock_popen:
            emit_status_event("started")
        mock_popen.assert_not_called()

    def test_no_session_id_skips_registry_but_sends_channel(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("CORTEX_SESSION_ID")
        with patch("nova.hooks.status_event.subprocess.Popen") as mock_popen:
            emit_status_event("started", "detail")

        # Only channel message, no registry update
        assert mock_popen.call_count == 1
        cmd = mock_popen.call_args_list[0][0][0]
        assert "message" in cmd


class TestFireAndForget:
    """Popen exceptions should be swallowed."""

    def test_registry_popen_failure_still_sends_channel(self):
        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise OSError("registry update failed")
            return MagicMock()

        with patch("nova.hooks.status_event.subprocess.Popen", side_effect=side_effect):
            emit_status_event("started", "detail")

        assert call_count == 2

    def test_channel_popen_failure_swallowed(self):
        with patch("nova.hooks.status_event.subprocess.Popen", side_effect=OSError("fail")):
            emit_status_event("started", "detail")  # Should not raise
