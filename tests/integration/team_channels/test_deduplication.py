"""
Test: message deduplication — atomic findOneAndUpdate prevents double delivery.

Spec ref: Channels MCP Server > Message Deduplication
"Combined with atomic findOneAndUpdate (status: 'pending' → 'delivered') to prevent
concurrent delivery."

Spec ref: Polling Loop
"Atomic claim — prevents double delivery"
"If findOneAndUpdate returns null (already claimed by concurrent process): skip silently"

The atomic MongoDB operation is the source of truth. Two concurrent processes both
attempting to claim the same message will get: one success, one None.
"""

from __future__ import annotations

import threading

import pytest
from pymongo.database import Database

from .conftest import _insert_message, _claim_message, _get_pending


class TestAtomicClaim:
    def test_concurrent_claims_only_one_succeeds(self, mongo_db: Database):
        """Simulates two concurrent MCP poll loops trying to claim the same message."""
        msg = _insert_message(
            mongo_db, from_="sender", to="target-session", content="Important notification"
        )

        results = []

        def try_claim():
            result = _claim_message(mongo_db, msg["_id"])
            results.append(result)

        t1 = threading.Thread(target=try_claim)
        t2 = threading.Thread(target=try_claim)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        successful = [r for r in results if r is not None]
        assert len(successful) == 1
        assert successful[0]["status"] == "delivered"

    def test_second_claim_of_delivered_message_returns_none(self, mongo_db: Database):
        msg = _insert_message(mongo_db, from_="sender", to="target", content="Message")

        first = _claim_message(mongo_db, msg["_id"])
        second = _claim_message(mongo_db, msg["_id"])

        assert first is not None
        assert second is None

    def test_five_concurrent_claims_yield_exactly_one_delivery(self, mongo_db: Database):
        msg = _insert_message(
            mongo_db, from_="sender", to="target-session", content="Test"
        )

        claims = []

        def try_claim():
            r = _claim_message(mongo_db, msg["_id"])
            if r is not None:
                claims.append(r)

        threads = [threading.Thread(target=try_claim) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(claims) == 1

        stored = mongo_db["messages"].find_one({"_id": msg["_id"]})
        assert stored["status"] == "delivered"

    def test_claim_filters_on_status_pending(self, mongo_db: Database):
        """The atomic update must filter status=pending to prevent re-delivery."""
        mongo_db["messages"].insert_one(
            {
                "_id": "msg_already_del",
                "from": "sender",
                "to": "target",
                "content": "Done",
                "meta": {},
                "status": "delivered",
                "created_at": "2026-03-26T10:00:00Z",
                "delivered_at": "2026-03-26T10:00:01Z",
            }
        )

        result = _claim_message(mongo_db, "msg_already_del")

        assert result is None

    def test_separate_messages_all_claimable(self, mongo_db: Database):
        """Deduplication is per-message — different messages are independent."""
        msg1 = _insert_message(mongo_db, from_="a", to="target", content="First")
        msg2 = _insert_message(mongo_db, from_="b", to="target", content="Second")

        claim1 = _claim_message(mongo_db, msg1["_id"])
        claim2 = _claim_message(mongo_db, msg2["_id"])

        assert claim1 is not None
        assert claim2 is not None

    def test_claimed_message_no_longer_returned_by_get_pending(self, mongo_db: Database):
        msg = _insert_message(mongo_db, from_="a", to="my-session", content="Test")

        _claim_message(mongo_db, msg["_id"])

        pending = _get_pending(mongo_db, "my-session")
        assert all(m["_id"] != msg["_id"] for m in pending)

    def test_get_messages_returns_both_pending_and_delivered(self, mongo_db: Database):
        """get_messages (context recovery) returns both statuses — unlike get_pending."""
        mongo_db["messages"].insert_many(
            [
                {
                    "_id": "msg_hist_del",
                    "from": "a",
                    "to": "my-session",
                    "content": "Delivered msg",
                    "meta": {},
                    "status": "delivered",
                    "created_at": "2026-03-26T10:00:00Z",
                    "delivered_at": "2026-03-26T10:00:01Z",
                },
                {
                    "_id": "msg_hist_pend",
                    "from": "b",
                    "to": "my-session",
                    "content": "Pending msg",
                    "meta": {},
                    "status": "pending",
                    "created_at": "2026-03-26T10:01:00Z",
                    "delivered_at": None,
                },
            ]
        )

        # get_messages returns both (for context recovery after compaction)
        all_msgs = list(
            mongo_db["messages"].find({
                "$or": [{"to": "my-session"}, {"from": "my-session"}],
                "created_at": {"$gt": "2026-03-26T09:00:00Z"},
            })
        )
        ids = {m["_id"] for m in all_msgs}
        assert "msg_hist_del" in ids
        assert "msg_hist_pend" in ids

    def test_delivered_at_timestamp_set_on_claim(self, mongo_db: Database):
        msg = _insert_message(mongo_db, from_="a", to="target", content="Test")
        assert msg["delivered_at"] is None

        claimed = _claim_message(mongo_db, msg["_id"])

        assert claimed["delivered_at"] is not None
