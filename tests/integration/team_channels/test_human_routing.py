"""
Test: human message routing.

Spec ref: Communication Model > Human Message Routing
"'human' is a reserved `to` value that bypasses session registry validation."
"Session → human: send_message(to='human', ...) → writes to MongoDB with to: 'human'"
"Human → session (via CLI): cortex team message → from: 'human', sender_type: 'human'"
"Delivery to human: Cortex daemon polls MongoDB for to='human' pending messages"
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from click.testing import CliRunner
from pymongo.database import Database

from cortex.cli import cli
from cortex.session_registry import MongoSessionRepo
from .conftest import _insert_message, _get_pending


class TestSessionToHuman:
    def test_message_to_human_written_to_mongodb(self, mongo_db: Database):
        """Simulates send_message(to='human', ...) from a team session."""
        msg = _insert_message(
            mongo_db,
            from_="feedback-endpoint",
            to="human",
            content="Found a bug in the migration. Should I fix it or flag it?",
            meta={"type": "notification", "sender_type": "agent", "priority": "normal"},
        )

        assert msg["to"] == "human"
        assert msg["from"] == "feedback-endpoint"
        assert msg["status"] == "pending"

        stored = mongo_db["messages"].find_one({"_id": msg["_id"]})
        assert stored is not None
        assert stored["to"] == "human"

    def test_multiple_sessions_can_message_human(self, mongo_db: Database):
        for session_name in ["session-a", "session-b", "session-c"]:
            _insert_message(
                mongo_db,
                from_=session_name,
                to="human",
                content=f"Update from {session_name}",
            )

        human_msgs = list(mongo_db["messages"].find({"to": "human"}))
        assert len(human_msgs) == 3

    def test_daemon_polls_pending_human_messages(self, mongo_db: Database):
        """The daemon polls for to='human' messages to deliver to Slack."""
        _insert_message(
            mongo_db,
            from_="feedback-endpoint",
            to="human",
            content="Done with my task",
        )

        pending_for_human = _get_pending(mongo_db, "human")

        assert len(pending_for_human) == 1
        assert pending_for_human[0]["to"] == "human"
        assert pending_for_human[0]["status"] == "pending"

    def test_human_messages_have_status_pending_for_daemon(self, mongo_db: Database):
        """Pending status allows daemon to poll and mark delivered after Slack send."""
        _insert_message(mongo_db, from_="session-a", to="human", content="Check the PR")

        doc = mongo_db["messages"].find_one({"to": "human"})
        assert doc["status"] == "pending"


class TestHumanToSession:
    def test_cli_message_human_keyword_succeeds(self, patch_db):
        """Sending to 'human' via CLI bypasses session registry — no error."""
        runner = CliRunner()
        result = runner.invoke(cli, ["team", "message", "human", "please review the PR"])

        assert result.exit_code == 0

    def test_cli_message_to_session_written_with_from_human(
        self, patch_db, session_repo: MongoSessionRepo
    ):
        """CLI always writes from='human' — it's the human operator sending."""
        session_repo.register(
            "s1", {"name": "feedback-endpoint", "team": "default", "task": "task"}
        )

        runner = CliRunner()
        runner.invoke(cli, ["team", "message", "feedback-endpoint", "stop, wrong direction"])

        doc = patch_db["messages"].find_one({"to": "feedback-endpoint"})
        assert doc["from"] == "human"

    def test_cli_message_has_human_sender_type(
        self, patch_db, session_repo: MongoSessionRepo
    ):
        session_repo.register(
            "s1", {"name": "target-session", "team": "default", "task": "task"}
        )

        runner = CliRunner()
        runner.invoke(cli, ["team", "message", "target-session", "check this out"])

        doc = patch_db["messages"].find_one({"to": "target-session"})
        assert doc["meta"]["sender_type"] == "human"

    def test_cli_human_to_human_writes_pending_message(self, patch_db):
        """cortex team message human '...' writes with to='human'."""
        runner = CliRunner()
        runner.invoke(cli, ["team", "message", "human", "check on the build"])

        doc = patch_db["messages"].find_one({"to": "human"})
        assert doc is not None
        assert doc["status"] == "pending"
        assert doc["from"] == "human"

    def test_human_message_has_high_priority(
        self, patch_db, session_repo: MongoSessionRepo
    ):
        """Human messages default to priority=high per the CLI implementation."""
        session_repo.register(
            "s1", {"name": "target-session", "team": "default", "task": "task"}
        )

        runner = CliRunner()
        runner.invoke(cli, ["team", "message", "target-session", "urgent review needed"])

        doc = patch_db["messages"].find_one({"to": "target-session"})
        assert doc["meta"]["priority"] == "high"

    def test_human_message_returns_success_json(
        self, patch_db, session_repo: MongoSessionRepo
    ):
        session_repo.register(
            "s1", {"name": "target-session", "team": "default", "task": "task"}
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["team", "message", "target-session", "hello"])

        output = json.loads(result.output)
        assert output["success"] is True
        assert "msg_id" in output
        assert output["to"] == "target-session"


class TestHumanIsNotInRegistry:
    def test_human_is_not_a_registered_session(self, session_repo: MongoSessionRepo):
        """The 'human' recipient is not a session in the registry — it's a routing keyword."""
        all_sessions = session_repo.list()
        names = [s.get("name") for s in all_sessions]
        assert "human" not in names

    def test_sending_to_human_does_not_create_session(
        self, patch_db, session_repo: MongoSessionRepo
    ):
        runner = CliRunner()
        runner.invoke(cli, ["team", "message", "human", "hello"])

        # No "human" session should have been created
        doc = session_repo.resolve("human")
        assert doc is None
