"""
Test: Suren (operator) message routing.

Spec ref: Communication Model > Suren Message Routing
- 'suren' is the reserved `to` value that bypasses session registry validation.
- 'human' is a deprecated alias for 'suren' — coerced on write.
- Session → Suren: send_message(to='suren', ...) → writes to MongoDB with to: 'suren'.
- Suren → session (via CLI): cortex session message → from: 'suren', sender_type: 'suren'.
- Delivery: Cortex daemon polls for to in ('suren', 'human') pending messages.
"""

from __future__ import annotations

import json

from click.testing import CliRunner
from pymongo.database import Database

from cortex.cli import cli
from cortex.session_registry import MongoSessionRepo
from .conftest import _get_pending, _insert_message


class TestSessionToSuren:
    def test_message_to_suren_written_to_mongodb(self, mongo_db: Database):
        """Simulates send_message(to='suren', ...) from a team session."""
        msg = _insert_message(
            mongo_db,
            from_="feedback-endpoint",
            to="suren",
            content="Found a bug in the migration. Should I fix it or flag it?",
            meta={"type": "notification", "sender_type": "agent", "priority": "normal"},
        )

        assert msg["to"] == "suren"
        assert msg["from"] == "feedback-endpoint"
        assert msg["status"] == "pending"

        stored = mongo_db["messages"].find_one({"_id": msg["_id"]})
        assert stored is not None
        assert stored["to"] == "suren"

    def test_multiple_sessions_can_message_suren(self, mongo_db: Database):
        for session_name in ["session-a", "session-b", "session-c"]:
            _insert_message(
                mongo_db,
                from_=session_name,
                to="suren",
                content=f"Update from {session_name}",
            )

        suren_msgs = list(mongo_db["messages"].find({"to": "suren"}))
        assert len(suren_msgs) == 3

    def test_daemon_polls_pending_suren_messages(self, mongo_db: Database):
        """The daemon polls for to='suren' messages to deliver to Slack."""
        _insert_message(
            mongo_db,
            from_="feedback-endpoint",
            to="suren",
            content="Done with my task",
        )

        pending_for_suren = _get_pending(mongo_db, "suren")

        assert len(pending_for_suren) == 1
        assert pending_for_suren[0]["to"] == "suren"
        assert pending_for_suren[0]["status"] == "pending"

    def test_suren_messages_have_status_pending_for_daemon(self, mongo_db: Database):
        """Pending status allows daemon to poll and mark delivered after Slack send."""
        _insert_message(mongo_db, from_="session-a", to="suren", content="Check the PR")

        doc = mongo_db["messages"].find_one({"to": "suren"})
        assert doc["status"] == "pending"


class TestSurenToSession:
    def test_cli_message_suren_keyword_succeeds(self, patch_db):
        """Sending to 'suren' via CLI bypasses session registry — no error."""
        runner = CliRunner()
        result = runner.invoke(cli, ["session", "message", "suren", "please review the PR"])

        assert result.exit_code == 0

    def test_cli_message_to_session_written_with_from_suren(
        self, patch_db, session_repo: MongoSessionRepo
    ):
        """CLI invoked by Suren (CORTEX_ACTOR=suren) writes from='suren'."""
        session_repo.register(
            "s1", {"name": "feedback-endpoint", "team": "default", "task": "task"}
        )

        runner = CliRunner()
        runner.invoke(cli, ["session", "message", "feedback-endpoint", "stop, wrong direction"])

        doc = patch_db["messages"].find_one({"to": "feedback-endpoint"})
        assert doc["from"] == "suren"

    def test_cli_message_has_suren_sender_type(
        self, patch_db, session_repo: MongoSessionRepo
    ):
        session_repo.register(
            "s1", {"name": "target-session", "team": "default", "task": "task"}
        )

        runner = CliRunner()
        runner.invoke(cli, ["session", "message", "target-session", "check this out"])

        doc = patch_db["messages"].find_one({"to": "target-session"})
        assert doc["meta"]["sender_type"] == "suren"

    def test_cli_suren_to_suren_writes_pending_message(self, patch_db):
        """cortex session message suren '...' writes with to='suren'."""
        runner = CliRunner()
        runner.invoke(cli, ["session", "message", "suren", "check on the build"])

        doc = patch_db["messages"].find_one({"to": "suren"})
        assert doc is not None
        assert doc["status"] == "pending"
        assert doc["from"] == "suren"

    def test_suren_message_has_high_priority(
        self, patch_db, session_repo: MongoSessionRepo
    ):
        """Messages from Suren default to priority=high per the CLI implementation."""
        session_repo.register(
            "s1", {"name": "target-session", "team": "default", "task": "task"}
        )

        runner = CliRunner()
        runner.invoke(cli, ["session", "message", "target-session", "urgent review needed"])

        doc = patch_db["messages"].find_one({"to": "target-session"})
        assert doc["meta"]["priority"] == "high"

    def test_suren_message_returns_success_json(
        self, patch_db, session_repo: MongoSessionRepo
    ):
        session_repo.register(
            "s1", {"name": "target-session", "team": "default", "task": "task"}
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["session", "message", "target-session", "hello"])

        output = json.loads(result.output)
        assert output["success"] is True
        assert "msg_id" in output
        assert output["to"] == "target-session"


class TestSurenIsNotInRegistry:
    def test_suren_is_not_a_registered_session(self, session_repo: MongoSessionRepo):
        """The 'suren' recipient is not a session in the registry — it's a routing keyword."""
        all_sessions = session_repo.list()
        names = [s.get("name") for s in all_sessions]
        assert "suren" not in names

    def test_sending_to_suren_does_not_create_session(
        self, patch_db, session_repo: MongoSessionRepo
    ):
        runner = CliRunner()
        runner.invoke(cli, ["session", "message", "suren", "hello"])

        doc = session_repo.resolve("suren")
        assert doc is None


class TestLegacyHumanAlias:
    def test_cli_message_to_human_is_coerced_to_suren(self, patch_db):
        """Legacy `to='human'` is accepted and rewritten to `to='suren'`."""
        runner = CliRunner()
        result = runner.invoke(cli, ["session", "message", "human", "legacy ping"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["success"] is True
        assert output["to"] == "suren"
        assert "warning" in output
        assert "deprecated" in output["warning"]

        suren_doc = patch_db["messages"].find_one({"to": "suren"})
        assert suren_doc is not None
        assert patch_db["messages"].find_one({"to": "human"}) is None

    def test_daemon_query_covers_legacy_human_messages(self, mongo_db: Database):
        """If a pre-rename message slipped in with to='human', the daemon poll picks it up."""
        from cortex.cron_executor import deliver_suren_messages

        _insert_message(mongo_db, from_="worker-1", to="human", content="old-style")
        _insert_message(mongo_db, from_="worker-2", to="suren", content="new-style")

        pending = list(
            mongo_db["messages"].find(
                {"to": {"$in": ["suren", "human"]}, "status": "pending"}
            )
        )
        assert len(pending) == 2

        # daemon call — safe to run without Slack (falls through to fallback)
        deliver_suren_messages(mongo_db)

        remaining = list(
            mongo_db["messages"].find(
                {"to": {"$in": ["suren", "human"]}, "status": "pending"}
            )
        )
        assert remaining == []
