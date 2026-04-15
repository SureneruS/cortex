"""
Test: recipient validation in cortex team message.

Spec ref: Communication Model > Cold Path
"MCP validates `to` against session registry. If target doesn't exist → returns error
{ success: false, error: 'Session ... not found' }. No silent writes to dead addresses."

Note: This validation is implemented in two places:
- Python CLI (cortex team message): validates before writing to MongoDB
- TS MCP (send_message tool): validates before writing to MongoDB
These tests cover the Python CLI validation.
"""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from cortex.cli import cli
from cortex.session_registry import MongoSessionRepo


class TestRecipientValidation:
    def test_send_to_nonexistent_session_returns_error(self, patch_db):
        runner = CliRunner()
        result = runner.invoke(cli, ["session", "message", "nonexistent-session", "hello"])

        assert result.exit_code != 0
        output = json.loads(result.output.strip())
        assert "error" in output
        assert "nonexistent-session" in output["error"]

    def test_send_to_completed_session_returns_error(self, patch_db, session_repo):
        session_repo.register(
            "sess-done",
            {"name": "done-session", "team": "default", "task": "task", "status": "completed"},
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["session", "message", "done-session", "hello"])

        assert result.exit_code != 0
        output = json.loads(result.output.strip())
        assert "error" in output

    def test_send_to_dead_session_returns_error(self, patch_db, session_repo):
        session_repo.register(
            "sess-dead",
            {"name": "dead-session", "team": "default", "task": "task", "status": "dead"},
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["session", "message", "dead-session", "hello"])

        assert result.exit_code != 0
        output = json.loads(result.output.strip())
        assert "error" in output

    def test_send_to_active_session_succeeds(self, patch_db, session_repo):
        session_repo.register(
            "sess-active",
            {"name": "active-session", "team": "default", "task": "task"},
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["session", "message", "active-session", "hello there"])

        assert result.exit_code == 0

    def test_no_message_written_for_nonexistent_session(self, patch_db):
        """No silent write to dead addresses — MongoDB must stay empty on validation failure."""
        runner = CliRunner()
        runner.invoke(cli, ["session", "message", "ghost-session", "hello"])

        count = patch_db["messages"].count_documents({"to": "ghost-session"})
        assert count == 0

    def test_send_to_idle_session_succeeds(self, patch_db, session_repo):
        """idle is a valid active status — should be reachable."""
        session_repo.register(
            "sess-idle",
            {"name": "idle-session", "team": "default", "task": "task", "status": "idle"},
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["session", "message", "idle-session", "status check"])

        assert result.exit_code == 0

    def test_validation_uses_name_not_session_id(self, patch_db, session_repo):
        """Addressing is by name — sending to a raw session_id should fail."""
        session_repo.register(
            "raw-sess-id",
            {"name": "my-session", "team": "default", "task": "task"},
        )

        runner = CliRunner()
        # Using the _id directly (not the name)
        result = runner.invoke(cli, ["session", "message", "raw-sess-id", "hello"])

        # raw-sess-id is the _id, not the name — should fail validation
        assert result.exit_code != 0

    def test_suren_reserved_keyword_bypasses_validation(self, patch_db):
        """Sending to 'suren' must not require a registered session."""
        runner = CliRunner()
        result = runner.invoke(cli, ["session", "message", "suren", "please review this"])

        assert result.exit_code == 0

    def test_legacy_human_keyword_is_accepted_and_coerced(self, patch_db):
        """Legacy 'human' still bypasses validation (it's coerced to 'suren')."""
        runner = CliRunner()
        result = runner.invoke(cli, ["session", "message", "human", "please review this"])

        assert result.exit_code == 0

    def test_suren_message_written_to_mongodb(self, patch_db):
        runner = CliRunner()
        runner.invoke(cli, ["session", "message", "suren", "check on the build please"])

        doc = patch_db["messages"].find_one({"to": "suren"})
        assert doc is not None
        assert doc["content"] == "check on the build please"

    def test_legacy_human_message_rewritten_to_suren(self, patch_db):
        """A `to='human'` write lands as `to='suren'` in MongoDB."""
        runner = CliRunner()
        runner.invoke(cli, ["session", "message", "human", "legacy build ping"])

        assert patch_db["messages"].find_one({"to": "human"}) is None
        doc = patch_db["messages"].find_one({"to": "suren"})
        assert doc is not None
        assert doc["content"] == "legacy build ping"
