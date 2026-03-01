from unittest.mock import MagicMock, patch

import nova.mcp_server as mod


def _reset():
    mod._poster = None
    mod._dm_channel = None
    mod._sender_name = None


def _setup_mock_poster():
    _reset()
    poster = MagicMock()
    poster.get_dm_channel.return_value = "D0ABC123"
    poster.post_notification.return_value = "111.222"
    poster.post_reply.return_value = "333.444"
    poster.get_replies.return_value = [
        {"user": "U0USER", "text": "hi", "ts": "111.222"},
    ]
    return poster


@patch.dict("os.environ", {"SLACK_BOT_TOKEN": "xoxb-test", "SLACK_TARGET_USER_ID": "U0USER"})
@patch("nova.mcp_server.SlackPoster")
def test_init_creates_poster_and_resolves_channel(mock_cls):
    _reset()
    mock_cls.return_value.get_dm_channel.return_value = "D0ABC123"
    poster, channel = mod._init()
    mock_cls.assert_called_once_with(bot_token="xoxb-test", target_user_id="U0USER")
    poster.get_dm_channel.assert_called_once()
    assert channel == "D0ABC123"


@patch.dict("os.environ", {"SLACK_BOT_TOKEN": "xoxb-test", "SLACK_TARGET_USER_ID": "U0USER"})
@patch("nova.mcp_server.SlackPoster")
def test_init_caches_on_second_call(mock_cls):
    _reset()
    mock_cls.return_value.get_dm_channel.return_value = "D0ABC123"
    mod._init()
    mod._init()
    mock_cls.assert_called_once()


def test_send_message():
    poster = _setup_mock_poster()
    mod._poster = poster
    mod._dm_channel = "D0ABC123"
    result = mod.send_message(text="hello")
    poster.post_notification.assert_called_once_with(
        channel="D0ABC123", text="hello", username=None
    )
    assert "111.222" in result


def test_reply_to_thread():
    poster = _setup_mock_poster()
    mod._poster = poster
    mod._dm_channel = "D0ABC123"
    result = mod.reply_to_thread(thread_ts="111.222", text="reply")
    poster.post_reply.assert_called_once_with(
        channel="D0ABC123", thread_ts="111.222", text="reply", username=None
    )
    assert "333.444" in result


def test_add_reaction():
    poster = _setup_mock_poster()
    mod._poster = poster
    mod._dm_channel = "D0ABC123"
    result = mod.add_reaction(timestamp="111.222", emoji="thumbsup")
    poster.add_reaction.assert_called_once_with(
        channel="D0ABC123", timestamp="111.222", emoji="thumbsup"
    )
    assert "added" in result.lower()


def test_read_replies():
    poster = _setup_mock_poster()
    mod._poster = poster
    mod._dm_channel = "D0ABC123"
    result = mod.read_replies(thread_ts="111.222")
    poster.get_replies.assert_called_once_with(channel="D0ABC123", thread_ts="111.222")
    assert len(result) == 1
    assert result[0]["text"] == "hi"


def test_send_message_with_sender_name():
    poster = _setup_mock_poster()
    mod._poster = poster
    mod._dm_channel = "D0ABC123"
    mod._sender_name = "Arc (Desktop)"
    result = mod.send_message(text="hello")
    poster.post_notification.assert_called_once_with(
        channel="D0ABC123", text="hello", username="Arc (Desktop)"
    )
    assert "111.222" in result


def test_reply_to_thread_with_sender_name():
    poster = _setup_mock_poster()
    mod._poster = poster
    mod._dm_channel = "D0ABC123"
    mod._sender_name = "Arc (Desktop)"
    result = mod.reply_to_thread(thread_ts="111.222", text="reply")
    poster.post_reply.assert_called_once_with(
        channel="D0ABC123", thread_ts="111.222", text="reply",
        username="Arc (Desktop)"
    )
    assert "333.444" in result
