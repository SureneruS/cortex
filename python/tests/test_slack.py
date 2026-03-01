from unittest.mock import MagicMock

from nova.slack import SlackPoster


def test_open_dm_channel():
    mock_client = MagicMock()
    mock_client.conversations_open.return_value = {
        "ok": True,
        "channel": {"id": "D0ABC123"},
    }
    poster = SlackPoster(bot_token="xoxb-test", target_user_id="U0USER")
    poster._client = mock_client
    channel = poster.get_dm_channel()
    assert channel == "D0ABC123"
    mock_client.conversations_open.assert_called_once_with(users=["U0USER"])


def test_post_notification_new_thread():
    mock_client = MagicMock()
    mock_client.chat_postMessage.return_value = {"ok": True, "ts": "111.222"}
    poster = SlackPoster(bot_token="xoxb-test", target_user_id="U0USER")
    poster._client = mock_client
    result = poster.post_notification(channel="D0ABC", text="hello", thread_ts=None)
    assert result == "111.222"
    call_kwargs = mock_client.chat_postMessage.call_args[1]
    assert call_kwargs["channel"] == "D0ABC"
    assert "thread_ts" not in call_kwargs


def test_post_notification_existing_thread():
    mock_client = MagicMock()
    mock_client.chat_postMessage.return_value = {"ok": True, "ts": "333.444"}
    poster = SlackPoster(bot_token="xoxb-test", target_user_id="U0USER")
    poster._client = mock_client
    result = poster.post_notification(channel="D0ABC", text="hello", thread_ts="111.222")
    assert result == "333.444"
    call_kwargs = mock_client.chat_postMessage.call_args[1]
    assert call_kwargs["thread_ts"] == "111.222"


def test_add_reaction():
    mock_client = MagicMock()
    mock_client.reactions_add.return_value = {"ok": True}
    poster = SlackPoster(bot_token="xoxb-test", target_user_id="U0USER")
    poster._client = mock_client
    poster.add_reaction(channel="D0ABC", timestamp="333.444", emoji="white_check_mark")
    mock_client.reactions_add.assert_called_once_with(
        channel="D0ABC", timestamp="333.444", name="white_check_mark"
    )


def test_get_replies():
    mock_client = MagicMock()
    mock_client.conversations_replies.return_value = {
        "ok": True,
        "messages": [
            {"user": "U0USER", "text": "parent", "ts": "111.222"},
            {"user": "U0BOT", "text": "reply", "ts": "111.333"},
        ],
    }
    poster = SlackPoster(bot_token="xoxb-test", target_user_id="U0USER")
    poster._client = mock_client
    replies = poster.get_replies(channel="D0ABC", thread_ts="111.222")
    mock_client.conversations_replies.assert_called_once_with(channel="D0ABC", ts="111.222")
    assert len(replies) == 2
    assert replies[0] == {"user": "U0USER", "text": "parent", "ts": "111.222"}
    assert replies[1] == {"user": "U0BOT", "text": "reply", "ts": "111.333"}
