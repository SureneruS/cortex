import json
from pathlib import Path
from unittest.mock import patch, MagicMock

from nova.hooks.notification import handle_notification, _format_message


def _make_state_file(tmp_path, sessions=None, slack=None):
    state_file = tmp_path / "state.json"
    data = {"last_dream_run": None, "sessions": sessions or {}, "slack": slack or {}}
    state_file.write_text(json.dumps(data))
    return state_file


def _make_session(**overrides):
    base = {
        "repos": ["rb"],
        "transcript_path": "",
        "memory_injected": True,
        "goal": "test goal",
        "started_at": "",
        "last_active_at": "",
        "tmux_target": "sessions:rb",
        "tmux_window": "rb",
        "slack_thread_ts": None,
        "slack_channel": None,
    }
    base.update(overrides)
    return base


class TestFormatMessage:
    def test_includes_window_name(self):
        msg = _format_message({"tmux_window": "rb", "goal": "fix bug"}, {})
        assert "*[rb]*" in msg

    def test_includes_goal(self):
        msg = _format_message({"tmux_window": "rb", "goal": "fix OAuth"}, {})
        assert "fix OAuth" in msg

    def test_omits_goal_when_empty(self):
        msg = _format_message({"tmux_window": "rb", "goal": ""}, {})
        assert "Goal:" not in msg

    def test_unknown_window_fallback(self):
        msg = _format_message({}, {})
        assert "*[unknown]*" in msg


class TestSkipConditions:
    def test_skips_empty_session_id(self, tmp_path):
        state_file = _make_state_file(tmp_path, {"s1": _make_session()})
        result = handle_notification({"session_id": ""}, state_file=state_file)
        assert result == {}

    def test_skips_missing_state_file(self, tmp_path):
        result = handle_notification(
            {"session_id": "s1"}, state_file=tmp_path / "missing.json"
        )
        assert result == {}

    def test_skips_unknown_session(self, tmp_path):
        state_file = _make_state_file(tmp_path)
        result = handle_notification({"session_id": "unknown"}, state_file=state_file)
        assert result == {}

    def test_skips_when_no_tmux_target(self, tmp_path):
        state_file = _make_state_file(
            tmp_path, {"sess1": _make_session(tmux_target=None)}
        )
        result = handle_notification({"session_id": "sess1"}, state_file=state_file)
        assert result == {}

    def test_skips_when_tmux_attached(self, tmp_path):
        state_file = _make_state_file(tmp_path, {"sess1": _make_session()})
        with patch("nova.hooks.notification.is_client_attached", return_value=True):
            result = handle_notification(
                {"session_id": "sess1"}, state_file=state_file
            )
        assert result == {}


class TestSlackPosting:
    def _run_with_mocks(self, tmp_path, session_overrides=None, slack_state=None):
        sessions = {"sess1": _make_session(**(session_overrides or {}))}
        state_file = _make_state_file(tmp_path, sessions, slack=slack_state)
        mock_config = {
            "slack": {"bot_token": "xoxb-test", "target_user_id": "U0USER"}
        }

        mock_poster = MagicMock()
        mock_poster.get_dm_channel.return_value = "D0ABC"
        mock_poster.post_notification.return_value = "111.222"

        with (
            patch("nova.hooks.notification.is_client_attached", return_value=False),
            patch("nova.hooks.notification.load_config", return_value=mock_config),
            patch("nova.hooks.notification.SlackPoster", return_value=mock_poster),
        ):
            result = handle_notification(
                {"session_id": "sess1"}, state_file=state_file
            )

        return result, mock_poster, state_file

    def test_posts_and_returns_empty_dict(self, tmp_path):
        result, mock_poster, _ = self._run_with_mocks(tmp_path)
        assert result == {}
        mock_poster.post_notification.assert_called_once()

    def test_opens_dm_when_no_channel(self, tmp_path):
        _, mock_poster, _ = self._run_with_mocks(tmp_path)
        mock_poster.get_dm_channel.assert_called_once()

    def test_saves_thread_ts_on_first_post(self, tmp_path):
        _, _, state_file = self._run_with_mocks(tmp_path)
        data = json.loads(state_file.read_text())
        assert data["sessions"]["sess1"]["slack_thread_ts"] == "111.222"
        assert data["sessions"]["sess1"]["slack_channel"] == "D0ABC"

    def test_saves_dm_channel_globally(self, tmp_path):
        _, _, state_file = self._run_with_mocks(tmp_path)
        data = json.loads(state_file.read_text())
        assert data["slack"]["dm_channel"] == "D0ABC"

    def test_reuses_cached_dm_channel(self, tmp_path):
        _, mock_poster, _ = self._run_with_mocks(
            tmp_path, slack_state={"dm_channel": "D0CACHED"}
        )
        mock_poster.get_dm_channel.assert_not_called()
        call_kwargs = mock_poster.post_notification.call_args[1]
        assert call_kwargs["channel"] == "D0CACHED"

    def test_reuses_existing_thread(self, tmp_path):
        _, mock_poster, _ = self._run_with_mocks(
            tmp_path,
            session_overrides={
                "slack_thread_ts": "existing.thread",
                "slack_channel": "D0ABC",
            },
        )
        call_kwargs = mock_poster.post_notification.call_args[1]
        assert call_kwargs["thread_ts"] == "existing.thread"

    def test_does_not_overwrite_existing_thread_ts(self, tmp_path):
        _, _, state_file = self._run_with_mocks(
            tmp_path,
            session_overrides={
                "slack_thread_ts": "existing.thread",
                "slack_channel": "D0ABC",
            },
        )
        data = json.loads(state_file.read_text())
        assert data["sessions"]["sess1"]["slack_thread_ts"] == "existing.thread"

    def test_session_channel_takes_priority(self, tmp_path):
        _, mock_poster, _ = self._run_with_mocks(
            tmp_path,
            session_overrides={"slack_channel": "D0SESSION"},
            slack_state={"dm_channel": "D0GLOBAL"},
        )
        mock_poster.get_dm_channel.assert_not_called()
        call_kwargs = mock_poster.post_notification.call_args[1]
        assert call_kwargs["channel"] == "D0SESSION"

    def test_message_contains_window_and_goal(self, tmp_path):
        _, mock_poster, _ = self._run_with_mocks(tmp_path)
        call_kwargs = mock_poster.post_notification.call_args[1]
        text = call_kwargs["text"]
        assert "*[rb]*" in text
        assert "test goal" in text
