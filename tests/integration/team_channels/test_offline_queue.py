"""
Test: messages written to MongoDB persist when the recipient is offline.

Spec ref: Communication Model > Offline delivery
"Messages persist in MongoDB. If the recipient is offline, messages queue until they
start a new session and the MCP polls for pending messages."

Spec ref: Channels MCP Server > Startup Sequence
"4. Deliver all pending messages (one-time initial delivery before poll loop starts)."
"""

from __future__ import annotations

import pytest
from pymongo.database import Database

from .conftest import _insert_message, _claim_message, _get_pending


class TestOfflineQueue:
    def test_messages_stay_pending_when_session_offline(self, mongo_db: Database):
        """Messages written before a session starts stay pending until claimed."""
        _insert_message(mongo_db, from_="auth-refactor", to="not-yet-started", content="Schema ready")

        pending = _get_pending(mongo_db, "not-yet-started")

        assert len(pending) == 1
        assert pending[0]["status"] == "pending"

    def test_multiple_offline_messages_all_queued(self, mongo_db: Database):
        for i in range(5):
            _insert_message(
                mongo_db,
                from_="sender",
                to="offline-session",
                content=f"Message {i}",
                created_at=f"2026-03-26T10:0{i}:00Z",
            )

        pending = _get_pending(mongo_db, "offline-session", limit=10)

        assert len(pending) == 5

    def test_startup_delivery_claims_all_pending(self, mongo_db: Database):
        """Simulates what the TS MCP does at startup: claim all pending messages."""
        for i in range(3):
            _insert_message(
                mongo_db,
                from_="other-session",
                to="my-session",
                content=f"Pre-startup message {i}",
                created_at=f"2026-03-26T09:0{i}:00Z",
            )

        pending = _get_pending(mongo_db, "my-session", limit=10)
        claimed_count = 0
        for msg in pending:
            result = _claim_message(mongo_db, msg["_id"])
            if result:
                claimed_count += 1

        assert claimed_count == 3
        still_pending = _get_pending(mongo_db, "my-session")
        assert len(still_pending) == 0

    def test_all_claimed_messages_are_delivered(self, mongo_db: Database):
        for i in range(3):
            _insert_message(mongo_db, from_="a", to="my-session", content=f"msg {i}")

        for msg in _get_pending(mongo_db, "my-session", limit=10):
            _claim_message(mongo_db, msg["_id"])

        all_msgs = list(mongo_db["messages"].find({"to": "my-session"}))
        assert all(m["status"] == "delivered" for m in all_msgs)

    def test_pending_messages_survive_fresh_repo_instance(self, mongo_db: Database):
        """Messages written in one 'session' are still there for the next (no in-memory leaks)."""
        _insert_message(
            mongo_db, from_="sender", to="target-session", content="Still here",
            created_at="2026-03-26T08:00:00Z",
        )

        # Simulate starting fresh (no in-memory state)
        fresh_pending = _get_pending(mongo_db, "target-session")

        assert len(fresh_pending) == 1
        assert fresh_pending[0]["content"] == "Still here"

    def test_get_pending_respects_limit(self, mongo_db: Database):
        for i in range(15):
            _insert_message(
                mongo_db, from_="a", to="limited-session", content=f"msg {i}",
                created_at=f"2026-03-26T10:{i:02d}:00Z",
            )

        pending = _get_pending(mongo_db, "limited-session", limit=10)

        assert len(pending) == 10

    def test_delivered_messages_not_returned_as_pending(self, mongo_db: Database):
        mongo_db["messages"].insert_many(
            [
                {
                    "_id": "msg_del_delivered",
                    "from": "a",
                    "to": "some-session",
                    "content": "Already delivered",
                    "meta": {},
                    "status": "delivered",
                    "created_at": "2026-03-26T10:00:00Z",
                    "delivered_at": "2026-03-26T10:00:01Z",
                },
                {
                    "_id": "msg_del_pending",
                    "from": "b",
                    "to": "some-session",
                    "content": "Still pending",
                    "meta": {},
                    "status": "pending",
                    "created_at": "2026-03-26T10:00:02Z",
                    "delivered_at": None,
                },
            ]
        )

        pending = _get_pending(mongo_db, "some-session")

        assert len(pending) == 1
        assert pending[0]["_id"] == "msg_del_pending"

    def test_messages_for_different_session_not_returned(self, mongo_db: Database):
        _insert_message(mongo_db, from_="a", to="session-a", content="for A")
        _insert_message(mongo_db, from_="b", to="session-b", content="for B")

        pending_a = _get_pending(mongo_db, "session-a")
        pending_b = _get_pending(mongo_db, "session-b")

        assert len(pending_a) == 1
        assert pending_a[0]["content"] == "for A"
        assert len(pending_b) == 1
        assert pending_b[0]["content"] == "for B"
