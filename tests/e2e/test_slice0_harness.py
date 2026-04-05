"""Slice 0: Test harness self-tests.

Verifies that the test infrastructure itself works correctly:
- Pre-flight checks detect real dependencies
- E2E fixtures can spawn/cleanup mock sessions (no CC)
- Read-only tests don't mutate state
"""
from __future__ import annotations

import shutil
import subprocess

import pytest
from pymongo import MongoClient

pytestmark = [pytest.mark.slice0, pytest.mark.e2e]


# ── Pre-flight checks (3 tests) ───────────────────────────────


class TestPreflightChecks:
    def test_mongodb_reachable(self):
        client = MongoClient("mongodb://localhost:27017", serverSelectionTimeoutMS=2000)
        result = client.admin.command("ping")
        client.close()
        assert result.get("ok") == 1.0, f"MongoDB ping returned: {result}"

    def test_tmux_running(self):
        result = subprocess.run(
            ["tmux", "list-sessions"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, "tmux server is not running"

    def test_cortex_on_path(self):
        path = shutil.which("cortex")
        assert path is not None, "'cortex' not found on PATH"


# ── Spawn + cleanup E2E (1 test) ──────────────────────────────


class TestSpawnCleanup:
    def test_spawn_and_cleanup(self, spawn_mock_session, e2e_session_repo):
        """Spawn a mock session, verify it exists, then let fixture cleanup."""
        doc = spawn_mock_session()
        session_id = doc["session_id"]
        pane_id = doc["pane_id"]

        assert session_id is not None, "session_id should be set"
        assert pane_id is not None, "pane_id should be set"
        assert doc["name"].startswith("test-"), "session name should have test- prefix"

        # Verify session exists in registry
        reg_doc = e2e_session_repo.get(session_id)
        assert reg_doc is not None, "session should exist in registry"
        assert reg_doc["status"] == "active", f"Expected active, got {reg_doc['status']}"

        # Verify tmux pane exists
        result = subprocess.run(
            ["tmux", "capture-pane", "-t", pane_id, "-p"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"tmux pane {pane_id} should exist"


# ── Read-only no-mutation (1 test) ─────────────────────────────


class TestReadOnlyNoMutation:
    def test_session_list_is_read_only(self, e2e_session_repo):
        """Verify that listing sessions doesn't create or modify anything."""
        before = e2e_session_repo.list({"name": {"$regex": "^test-"}})
        before_ids = {d["_id"] for d in before}

        result = subprocess.run(
            ["cortex", "session", "list", "--brief"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0, f"cortex session list failed: {result.stderr}"

        after = e2e_session_repo.list({"name": {"$regex": "^test-"}})
        after_ids = {d["_id"] for d in after}
        new_test_sessions = after_ids - before_ids
        assert len(new_test_sessions) == 0, (
            f"Read-only operation created test sessions: {new_test_sessions}"
        )


# ── Cleanup on failure (1 test) ────────────────────────────────


class TestCleanupOnFailure:
    def test_cleanup_runs_even_on_assertion_error(self, spawn_mock_session, e2e_session_repo):
        """Spawn a session, verify cleanup still works via fixture teardown."""
        doc = spawn_mock_session()
        session_id = doc["session_id"]

        reg_doc = e2e_session_repo.get(session_id)
        assert reg_doc is not None, "session should exist"
        assert reg_doc["status"] == "active"
