"""
Test: message write → MongoDB state.

Spec ref: MongoDB Collections > messages
Spec ref: Communication Model > Cold Path
"Always write to MongoDB first (status: 'pending'), then deliver."

Tests write messages using the CLI (cortex team message) or direct MongoDB helpers
that mirror what the TS MCP's send_message tool does.
"""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner
from pymongo.database import Database

from cortex.cli import cli
from cortex.session_registry import MongoSessionRepo
from .conftest import _insert_message, _claim_message


class TestMessageDocument:
    def test_written_message_has_pending_status(self, mongo_db: Database, session_repo):
        """Messages must be written with status=pending."""
        session_repo.register("s1", {"name": "target", "team": "default", "task": "task"})

        msg = _insert_message(mongo_db, from_="sender", to="target", content="Hello")

        stored = mongo_db["messages"].find_one({"_id": msg["_id"]})
        assert stored["status"] == "pending"

    def test_message_contains_required_fields(self, mongo_db: Database, session_repo):
        session_repo.register("s1", {"name": "target", "team": "default", "task": "task"})

        msg = _insert_message(mongo_db, from_="auth-refactor", to="target", content="Schema ready")

        assert msg["from"] == "auth-refactor"
        assert msg["to"] == "target"
        assert msg["content"] == "Schema ready"
        assert "created_at" in msg
        assert msg["delivered_at"] is None
        assert "_id" in msg

    def test_message_meta_fields_stored(self, mongo_db: Database, session_repo):
        session_repo.register("s1", {"name": "target", "team": "default", "task": "task"})

        msg = _insert_message(
            mongo_db,
            from_="sender",
            to="target",
            content="Request",
            meta={"type": "request", "priority": "high", "thread_id": "t_abc123"},
        )

        stored = mongo_db["messages"].find_one({"_id": msg["_id"]})
        assert stored["meta"]["type"] == "request"
        assert stored["meta"]["priority"] == "high"
        assert stored["meta"]["thread_id"] == "t_abc123"

    def test_from_field_is_at_top_level(self, mongo_db: Database):
        """from must be top-level for efficient polling queries (not nested in meta)."""
        msg = _insert_message(mongo_db, from_="auth-refactor", to="my-session", content="Done")

        stored = mongo_db["messages"].find_one({"_id": msg["_id"]})
        assert "from" in stored
        assert stored["from"] == "auth-refactor"

    def test_each_message_gets_unique_id(self, mongo_db: Database, session_repo):
        session_repo.register("s1", {"name": "target", "team": "default", "task": "task"})

        msg1 = _insert_message(mongo_db, from_="a", to="target", content="First")
        msg2 = _insert_message(mongo_db, from_="a", to="target", content="Second")

        assert msg1["_id"] != msg2["_id"]


class TestClaimTransition:
    def test_claim_transitions_to_delivered(self, mongo_db: Database):
        msg = _insert_message(mongo_db, from_="sender", to="target", content="Hi")

        claimed = _claim_message(mongo_db, msg["_id"])

        assert claimed is not None
        assert claimed["status"] == "delivered"
        assert claimed["delivered_at"] is not None

    def test_claim_nonexistent_returns_none(self, mongo_db: Database):
        result = _claim_message(mongo_db, "msg_nonexistent")
        assert result is None

    def test_claim_already_delivered_returns_none(self, mongo_db: Database):
        """Claiming an already-delivered message returns None — prevents double delivery."""
        msg = _insert_message(mongo_db, from_="sender", to="target", content="Hi")

        _claim_message(mongo_db, msg["_id"])
        second = _claim_message(mongo_db, msg["_id"])

        assert second is None

    def test_delivered_message_not_in_pending_query(self, mongo_db: Database):
        msg = _insert_message(mongo_db, from_="a", to="my-session", content="Test")
        _claim_message(mongo_db, msg["_id"])

        from .conftest import _get_pending

        pending = _get_pending(mongo_db, "my-session")
        assert all(m["_id"] != msg["_id"] for m in pending)


class TestCLIMessageDelivery:
    def test_cli_team_message_writes_to_mongodb(self, patch_db, session_repo):
        session_repo.register("s1", {"name": "feedback-endpoint", "team": "default", "task": "t"})

        runner = CliRunner()
        result = runner.invoke(cli, ["session", "message", "feedback-endpoint", "Schema is ready"])

        assert result.exit_code == 0
        doc = patch_db["messages"].find_one({"to": "feedback-endpoint"})
        assert doc is not None
        assert doc["content"] == "Schema is ready"
        assert doc["status"] == "pending"

    def test_cli_message_has_correct_from_field(self, patch_db, session_repo):
        session_repo.register("s1", {"name": "target-session", "team": "default", "task": "t"})

        runner = CliRunner()
        runner.invoke(cli, ["session", "message", "target-session", "hello"])

        doc = patch_db["messages"].find_one({"to": "target-session"})
        assert doc["from"] == "suren"

    def test_cli_message_returns_success_json(self, patch_db, session_repo):
        session_repo.register("s1", {"name": "target-session", "team": "default", "task": "t"})

        runner = CliRunner()
        result = runner.invoke(cli, ["session", "message", "target-session", "test"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["success"] is True
        assert "msg_id" in output

    def test_cli_message_sets_suren_sender_type(self, patch_db, session_repo):
        session_repo.register("s1", {"name": "target-session", "team": "default", "task": "t"})

        runner = CliRunner()
        runner.invoke(cli, ["session", "message", "target-session", "check this"])

        doc = patch_db["messages"].find_one({"to": "target-session"})
        assert doc["meta"]["sender_type"] == "suren"

    def test_pending_messages_queryable_before_delivery(self, mongo_db: Database, session_repo):
        session_repo.register("s1", {"name": "target", "team": "default", "task": "t"})

        _insert_message(mongo_db, from_="a", to="target", content="msg1")
        _insert_message(mongo_db, from_="b", to="target", content="msg2")

        from .conftest import _get_pending

        pending = _get_pending(mongo_db, "target")
        assert len(pending) == 2
        assert all(m["status"] == "pending" for m in pending)

    def test_pending_sorted_oldest_first(self, mongo_db: Database, session_repo):
        """Delivery order must be oldest first."""
        session_repo.register("s1", {"name": "target", "team": "default", "task": "t"})

        _insert_message(
            mongo_db, from_="a", to="target", content="first",
            created_at="2026-03-26T10:00:00Z",
        )
        _insert_message(
            mongo_db, from_="b", to="target", content="second",
            created_at="2026-03-26T10:01:00Z",
        )

        from .conftest import _get_pending

        pending = _get_pending(mongo_db, "target", limit=10)
        assert pending[0]["content"] == "first"
        assert pending[1]["content"] == "second"
