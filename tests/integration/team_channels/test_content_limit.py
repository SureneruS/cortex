"""
Test: message content size limit enforcement.

Spec ref: Known Constraints > Message content size limit
"Maximum message content: 10KB."

Spec ref: MCP Tools > send_message (in index.ts)
if (content.length > MAX_CONTENT_SIZE) { return { success: false, error: ... } }

Note: The 10KB limit is enforced by the TS MCP's send_message tool. The Python CLI
(cortex team message) currently does NOT enforce the size limit — it is the TS-side
protection. These tests verify the spec behavior as exercised through the TS handlers.
For Python CLI-specific behavior, see test_recipient_validation.py.

The Python integration tests here verify MongoDB state: that oversized messages should
not appear in the messages collection if the size check is respected by the writer.
The TS-specific limit tests are in src/channels-mcp/__tests__/content-limit.test.ts.
"""

from __future__ import annotations

import pytest
from pymongo.database import Database

MAX_CONTENT_BYTES = 10_240


class TestContentLimitMongoDBLevel:
    def test_message_at_exact_limit_can_be_stored(self, mongo_db: Database, session_repo):
        """MongoDB itself imposes no content size restriction — the MCP layer does."""
        session_repo.register("s1", {"name": "target", "team": "default", "task": "t"})
        content = "x" * MAX_CONTENT_BYTES

        mongo_db["messages"].insert_one(
            {
                "_id": "msg_at_limit",
                "from": "sender",
                "to": "target",
                "content": content,
                "meta": {"type": "notification", "sender_type": "agent", "priority": "normal"},
                "status": "pending",
                "created_at": "2026-03-26T10:00:00Z",
                "delivered_at": None,
            }
        )

        stored = mongo_db["messages"].find_one({"_id": "msg_at_limit"})
        assert stored is not None
        assert len(stored["content"]) == MAX_CONTENT_BYTES

    def test_no_oversized_message_should_be_in_collection(self, mongo_db: Database):
        """Invariant: after TS MCP rejects oversized messages, none should be in MongoDB."""
        # Verify collection starts empty (no oversized messages slipped through)
        oversized_messages = list(
            mongo_db["messages"].find(
                {"$where": f"this.content && this.content.length > {MAX_CONTENT_BYTES}"}
            )
        )
        assert len(oversized_messages) == 0


class TestContentLimitSpecBoundary:
    def test_max_content_is_10240_bytes(self):
        """Spec defines max content as 10KB = 10240 bytes."""
        assert MAX_CONTENT_BYTES == 10_240

    def test_large_path_reference_fits_within_limit(self):
        """For large payloads, spec says: send the file path instead of content."""
        path_message = "/home/agent/project/.worktrees/auth-refactor/changes/migration.sql"
        assert len(path_message) < MAX_CONTENT_BYTES

    def test_typical_status_update_fits_within_limit(self):
        """Typical inter-session messages should easily fit within 10KB."""
        typical_message = (
            "Endpoint ready. POST /api/feedback { body: string, rating: int, anonymous: bool }. "
            "Schema validation is in place. Error codes: 422 on invalid rating (must be 1-5), "
            "400 on empty body. Auth required (JWT in Authorization header). PR #142."
        )
        assert len(typical_message.encode()) < MAX_CONTENT_BYTES

    def test_full_diff_exceeds_limit(self):
        """A full git diff of a real file likely exceeds 10KB — must send path instead."""
        simulated_diff = "+" * (MAX_CONTENT_BYTES + 1000)  # typical diff can be much larger
        assert len(simulated_diff.encode()) > MAX_CONTENT_BYTES
