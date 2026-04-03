"""
Test: human reply routing via Slack.

Covers bidirectional human<->session messaging:
- Outbound: session messages grouped into one Slack thread per session
- Inbound: human replies in Slack thread routed back to originating session
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from pymongo.database import Database

from cortex.cron_executor import (
    deliver_human_messages,
    handle_slack_message_event,
    _thread_session_map,
)
from cortex.session_registry import MongoSessionRepo
from .conftest import _insert_message, _utc_now


FAKE_SLACK_TS = "1712345678.000100"
FAKE_SLACK_CHANNEL = "D0ABC123"
FAKE_BOT_USER_ID = "U_BOT"


@pytest.fixture(autouse=True)
def clear_thread_cache():
    _thread_session_map.clear()
    yield
    _thread_session_map.clear()


@pytest.fixture
def mock_slack():
    poster = MagicMock()
    poster.post_notification.return_value = FAKE_SLACK_TS
    poster.post_reply.return_value = "1712345679.000150"
    with patch("cortex.cron_executor._get_slack", return_value=(poster, FAKE_SLACK_CHANNEL)):
        yield poster


class TestOutboundThreading:
    """First message from a session creates a new Slack thread; subsequent messages reuse it."""

    def test_first_message_creates_new_thread(
        self, mongo_db: Database, session_repo: MongoSessionRepo, mock_slack
    ):
        session_repo.register("s1", {"name": "worker-1", "status": "active"})
        _insert_message(mongo_db, from_="worker-1", to="human", content="First message")

        deliver_human_messages(mongo_db)

        mock_slack.post_notification.assert_called_once()
        call_kwargs = mock_slack.post_notification.call_args
        assert call_kwargs.kwargs.get("thread_ts") is None or "thread_ts" not in call_kwargs.kwargs

    def test_first_message_stores_thread_ts_on_session(
        self, mongo_db: Database, session_repo: MongoSessionRepo, mock_slack
    ):
        session_repo.register("s1", {"name": "worker-1", "status": "active"})
        _insert_message(mongo_db, from_="worker-1", to="human", content="First message")

        deliver_human_messages(mongo_db)

        session = session_repo.resolve("worker-1")
        assert session["slack_thread_ts"] == FAKE_SLACK_TS
        assert session["slack_channel"] == FAKE_SLACK_CHANNEL

    def test_second_message_uses_existing_thread(
        self, mongo_db: Database, session_repo: MongoSessionRepo, mock_slack
    ):
        session_repo.register("s1", {"name": "worker-1", "status": "active"})
        # Simulate first message already delivered — session has thread_ts
        session_repo.update("s1", {"slack_thread_ts": FAKE_SLACK_TS, "slack_channel": FAKE_SLACK_CHANNEL})

        _insert_message(mongo_db, from_="worker-1", to="human", content="Second message")

        deliver_human_messages(mongo_db)

        mock_slack.post_notification.assert_called_once()
        call_kwargs = mock_slack.post_notification.call_args
        assert call_kwargs.kwargs.get("thread_ts") == FAKE_SLACK_TS

    def test_different_sessions_get_different_threads(
        self, mongo_db: Database, session_repo: MongoSessionRepo, mock_slack
    ):
        session_repo.register("s1", {"name": "worker-1", "status": "active"})
        session_repo.register("s2", {"name": "worker-2", "status": "active"})

        mock_slack.post_notification.side_effect = ["1712345678.000100", "1712345678.000200"]

        _insert_message(mongo_db, from_="worker-1", to="human", content="From worker 1")
        _insert_message(mongo_db, from_="worker-2", to="human", content="From worker 2")

        deliver_human_messages(mongo_db)

        s1 = session_repo.resolve("worker-1")
        s2 = session_repo.resolve("worker-2")
        assert s1["slack_thread_ts"] != s2["slack_thread_ts"]

    def test_thread_ts_cached_in_memory(
        self, mongo_db: Database, session_repo: MongoSessionRepo, mock_slack
    ):
        session_repo.register("s1", {"name": "worker-1", "status": "active"})
        _insert_message(mongo_db, from_="worker-1", to="human", content="First")

        deliver_human_messages(mongo_db)

        assert _thread_session_map.get(FAKE_SLACK_TS) == "worker-1"


class TestInboundRouting:
    """Human replies in Slack thread are routed back to the originating session."""

    def test_threaded_reply_creates_pending_message(self, mongo_db: Database):
        _thread_session_map[FAKE_SLACK_TS] = "worker-1"

        handle_slack_message_event(
            mongo_db,
            user="U_HUMAN",
            text="Yes, go ahead",
            thread_ts=FAKE_SLACK_TS,
            ts="1712345680.000200",
            channel=FAKE_SLACK_CHANNEL,
            bot_user_id=FAKE_BOT_USER_ID,
        )

        reply = mongo_db["messages"].find_one({"from": "human", "to": "worker-1"})
        assert reply is not None
        assert reply["content"] == "Yes, go ahead"
        assert reply["status"] == "pending"
        assert reply["meta"]["type"] == "reply"
        assert reply["meta"]["sender_type"] == "human"
        assert reply["meta"]["priority"] == "high"

    def test_bot_replies_ignored(self, mongo_db: Database):
        _thread_session_map[FAKE_SLACK_TS] = "worker-1"

        handle_slack_message_event(
            mongo_db,
            user=FAKE_BOT_USER_ID,
            text="Bot echo",
            thread_ts=FAKE_SLACK_TS,
            ts="1712345680.000200",
            channel=FAKE_SLACK_CHANNEL,
            bot_user_id=FAKE_BOT_USER_ID,
        )

        replies = list(mongo_db["messages"].find({"from": "human"}))
        assert len(replies) == 0

    def test_non_threaded_message_ignored(self, mongo_db: Database):
        handle_slack_message_event(
            mongo_db,
            user="U_HUMAN",
            text="Random DM",
            thread_ts=None,
            ts="1712345680.000200",
            channel=FAKE_SLACK_CHANNEL,
            bot_user_id=FAKE_BOT_USER_ID,
        )

        replies = list(mongo_db["messages"].find({"from": "human"}))
        assert len(replies) == 0

    def test_unknown_thread_ignored(self, mongo_db: Database):
        handle_slack_message_event(
            mongo_db,
            user="U_HUMAN",
            text="Reply to unknown thread",
            thread_ts="9999999999.000000",
            ts="1712345680.000200",
            channel=FAKE_SLACK_CHANNEL,
            bot_user_id=FAKE_BOT_USER_ID,
        )

        replies = list(mongo_db["messages"].find({"from": "human"}))
        assert len(replies) == 0

    def test_cache_miss_falls_back_to_db(
        self, mongo_db: Database, session_repo: MongoSessionRepo
    ):
        """After daemon restart, cache is empty but DB has the mapping."""
        session_repo.register("s1", {
            "name": "worker-1",
            "status": "active",
            "slack_thread_ts": FAKE_SLACK_TS,
            "slack_channel": FAKE_SLACK_CHANNEL,
        })

        handle_slack_message_event(
            mongo_db,
            user="U_HUMAN",
            text="Reply after restart",
            thread_ts=FAKE_SLACK_TS,
            ts="1712345680.000200",
            channel=FAKE_SLACK_CHANNEL,
            bot_user_id=FAKE_BOT_USER_ID,
        )

        reply = mongo_db["messages"].find_one({"from": "human", "to": "worker-1"})
        assert reply is not None
        # Cache should be repopulated
        assert _thread_session_map[FAKE_SLACK_TS] == "worker-1"

    def test_multiple_replies_each_create_message(self, mongo_db: Database):
        _thread_session_map[FAKE_SLACK_TS] = "worker-1"

        for i, ts in enumerate(["1712345680.000200", "1712345680.000300"]):
            handle_slack_message_event(
                mongo_db,
                user="U_HUMAN",
                text=f"Reply {i}",
                thread_ts=FAKE_SLACK_TS,
                ts=ts,
                channel=FAKE_SLACK_CHANNEL,
                bot_user_id=FAKE_BOT_USER_ID,
            )

        replies = list(mongo_db["messages"].find({"from": "human", "to": "worker-1"}))
        assert len(replies) == 2
