"""Tests for status_event.py — channel emission + registry updates."""

from __future__ import annotations

import json
from unittest.mock import patch, MagicMock

import pytest

from nova.hooks.status_event import emit_status_event, _EVENT_TO_RUNTIME, MAJOR_EVENTS


@pytest.fixture(autouse=True)
def _set_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CORTEX_SESSION_NAME", "worker-1")
    monkeypatch.setenv("CORTEX_PARENT_NAME", "control-main")
    monkeypatch.setenv("CORTEX_SESSION_ID", "sess-abc-123")


class TestRegistryUpdate:
    """All events update last_event; mapped events also update runtime."""

    @pytest.mark.parametrize("event,expected_runtime", list(_EVENT_TO_RUNTIME.items()))
    def test_mapped_events_update_registry(self, event: str, expected_runtime: str):
        with patch("nova.hooks.status_event.subprocess.Popen") as mock_popen:
            emit_status_event(event, "some detail")

        # Calls: last_event update + runtime update + channel (if major)
        is_major = event in MAJOR_EVENTS
        expected_calls = 3 if is_major else 2
        assert mock_popen.call_count == expected_calls

        # First call: last_event registry update
        last_event_cmd = mock_popen.call_args_list[0][0][0]
        assert last_event_cmd[:4] == ["cortex", "--json", "session", "update"]
        assert "worker-1" in last_event_cmd
        data_idx = last_event_cmd.index("--data") + 1
        data = json.loads(last_event_cmd[data_idx])
        assert data["last_event"] == event

        # Second call: runtime registry update
        runtime_cmd = mock_popen.call_args_list[1][0][0]
        assert runtime_cmd[:4] == ["cortex", "--json", "session", "update"]
        assert "sess-abc-123" in runtime_cmd
        data_idx = runtime_cmd.index("--data") + 1
        assert json.loads(runtime_cmd[data_idx]) == {"runtime": expected_runtime}

    def test_done_event_skips_runtime_update(self):
        with patch("nova.hooks.status_event.subprocess.Popen") as mock_popen:
            emit_status_event("done", "Session ended")

        # last_event update + channel message (done is major, but not in runtime map)
        assert mock_popen.call_count == 2
        last_event_cmd = mock_popen.call_args_list[0][0][0]
        assert "update" in last_event_cmd
        channel_cmd = mock_popen.call_args_list[1][0][0]
        assert "message" in channel_cmd

    def test_unknown_event_only_updates_last_event(self):
        with patch("nova.hooks.status_event.subprocess.Popen") as mock_popen:
            emit_status_event("some_unknown_event")

        # Only last_event registry update (not major, not mapped)
        assert mock_popen.call_count == 1
        cmd = mock_popen.call_args_list[0][0][0]
        assert "update" in cmd


class TestMajorMinorSplit:
    """Only major events send channel messages to parent."""

    @pytest.mark.parametrize("event", sorted(MAJOR_EVENTS))
    def test_major_events_send_channel_message(self, event: str):
        with patch("nova.hooks.status_event.subprocess.Popen") as mock_popen:
            emit_status_event(event, "detail")

        # Last Popen call should be the channel message
        channel_cmd = mock_popen.call_args_list[-1][0][0]
        assert channel_cmd[:4] == ["cortex", "--json", "session", "message"]
        assert "control-main" in channel_cmd

    @pytest.mark.parametrize("event", ["turn_completed", "progress", "editing_file", "committed"])
    def test_minor_events_skip_channel_message(self, event: str):
        with patch("nova.hooks.status_event.subprocess.Popen") as mock_popen:
            emit_status_event(event, "detail")

        # No channel message — only registry updates
        for c in mock_popen.call_args_list:
            cmd = c[0][0]
            assert "message" not in cmd


class TestChannelMessage:
    """Channel message to parent should be sent for major events."""

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

    def test_no_parent_skips_channel_but_updates_registry(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("CORTEX_PARENT_NAME")
        with patch("nova.hooks.status_event.subprocess.Popen") as mock_popen:
            emit_status_event("started", "detail")

        # last_event + runtime update, but no channel message
        assert mock_popen.call_count == 2
        for c in mock_popen.call_args_list:
            cmd = c[0][0]
            assert "message" not in cmd

    def test_no_session_id_skips_runtime_but_sends_rest(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("CORTEX_SESSION_ID")
        with patch("nova.hooks.status_event.subprocess.Popen") as mock_popen:
            emit_status_event("started", "detail")

        # last_event update + channel message (no runtime since no session_id)
        assert mock_popen.call_count == 2
        cmds = [c[0][0] for c in mock_popen.call_args_list]
        assert "update" in cmds[0]
        assert "message" in cmds[1]


class TestFireAndForget:
    """Popen exceptions should be swallowed."""

    def test_registry_popen_failure_still_sends_channel(self):
        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise OSError("last_event update failed")
            return MagicMock()

        with patch("nova.hooks.status_event.subprocess.Popen", side_effect=side_effect):
            emit_status_event("started", "detail")

        # 3 attempts: last_event (fails) + runtime + channel
        assert call_count == 3

    def test_channel_popen_failure_swallowed(self):
        with patch("nova.hooks.status_event.subprocess.Popen", side_effect=OSError("fail")):
            emit_status_event("started", "detail")  # Should not raise
