import json
from pathlib import Path
from unittest.mock import patch, MagicMock

from nova.exchange import ExchangeHandler


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
        "goal": "test",
        "started_at": "",
        "last_active_at": "",
        "tmux_target": "sessions:rb",
        "tmux_window": "rb",
        "slack_thread_ts": "111.222",
        "slack_channel": "D0ABC",
    }
    base.update(overrides)
    return base


def test_routes_reply_to_session(tmp_path):
    state_file = _make_state_file(tmp_path, sessions={"sess1": _make_session()})
    handler = ExchangeHandler(state_file=state_file)

    with (
        patch("nova.exchange.has_window", return_value=True),
        patch("nova.exchange.send_keys") as mock_send,
    ):
        result = handler.handle_message(
            channel="D0ABC",
            thread_ts="111.222",
            message_ts="333.444",
            text="continue with the tests",
            user="U0USER",
        )

    assert result is True
    mock_send.assert_called_once_with("sessions:rb", "continue with the tests")


def test_ignores_non_session_thread(tmp_path):
    state_file = _make_state_file(tmp_path)
    handler = ExchangeHandler(state_file=state_file)
    result = handler.handle_message(
        channel="D0ABC",
        thread_ts="999.999",
        message_ts="444.555",
        text="random",
        user="U0USER",
    )
    assert result is False


def test_replies_if_session_dead(tmp_path):
    state_file = _make_state_file(tmp_path, sessions={"sess1": _make_session()})
    handler = ExchangeHandler(state_file=state_file)
    mock_poster = MagicMock()
    handler._poster = mock_poster

    with patch("nova.exchange.has_window", return_value=False):
        result = handler.handle_message(
            channel="D0ABC",
            thread_ts="111.222",
            message_ts="555.666",
            text="hello",
            user="U0USER",
        )

    assert result is False
    mock_poster.post_reply.assert_called_once()
    assert "no longer active" in mock_poster.post_reply.call_args.kwargs["text"]


def test_ignores_bot_messages(tmp_path):
    state_file = _make_state_file(tmp_path, slack={"bot_user_id": "U0BOT"})
    handler = ExchangeHandler(state_file=state_file)
    result = handler.handle_message(
        channel="D0ABC",
        thread_ts="111.222",
        message_ts="666.777",
        text="I posted this",
        user="U0BOT",
    )
    assert result is False
