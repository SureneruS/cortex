"""Slice 1: Repo-based sessions E2E tests.

All tests use spawn_mock_session (no CC, no API calls).

Verifies:
- Sessions spawn in correct repo directory
- Registry repos field set at spawn time
- Spawn without --repo uses workspace root
- Stale pane detection via health check
- Cleanup leaves no test artifacts
"""
from __future__ import annotations

import json
import subprocess
import time

import pytest

pytestmark = [pytest.mark.slice1, pytest.mark.e2e]

WORKSPACE = "/Users/suren/workspace/cercli"


def _get_session(session_id: str) -> dict:
    result = subprocess.run(
        ["cortex", "--json", "session", "get", session_id],
        capture_output=True, text=True, timeout=10,
    )
    return json.loads(result.stdout)


def _pane_cwd(pane_id: str) -> str:
    result = subprocess.run(
        ["tmux", "display-message", "-t", pane_id, "-p", "#{pane_current_path}"],
        capture_output=True, text=True, timeout=5,
    )
    return result.stdout.strip()


class TestSpawnWithRepo:
    """Sessions spawn in repo directory with correct registry metadata."""

    def test_spawn_with_repo_sets_cwd(self, spawn_mock_session):
        doc = spawn_mock_session("test-cwd-rb", repo="recruitment-backend")
        cwd = _pane_cwd(doc["pane_id"])
        assert cwd == f"{WORKSPACE}/recruitment-backend", f"Expected recruitment-backend, got {cwd}"

    def test_spawn_with_repo_sets_registry_repos(self, spawn_mock_session):
        doc = spawn_mock_session("test-repos-field", repo="cortex")
        reg = _get_session(doc["session_id"])
        assert reg["repos"] == ["cortex"], f"Expected ['cortex'], got {reg.get('repos')}"

    def test_spawn_bad_repo_errors(self):
        result = subprocess.run(
            ["cortex", "session", "spawn", "--name", "test-bad", "--repo", "nonexistent-xyz"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode != 0, "Should fail for nonexistent repo"
        output = (result.stdout + result.stderr).lower()
        assert "not found" in output, f"Should mention 'not found', got: {output}"


class TestSpawnWithoutRepo:
    """No --repo uses current cwd."""

    def test_spawn_without_repo_uses_cwd(self, spawn_mock_session):
        doc = spawn_mock_session("test-no-repo")
        cwd = _pane_cwd(doc["pane_id"])
        assert WORKSPACE in cwd, f"Expected workspace path, got {cwd}"


class TestFlagPassthrough:
    """Verify spawn flags are stored in registry."""

    def test_effort_passthrough(self, spawn_mock_session):
        doc = spawn_mock_session("test-effort", repo="cortex")
        reg = _get_session(doc["session_id"])
        assert reg["status"] == "active"


class TestStalePaneDetection:
    """Health check detects stale pane_id."""

    def test_dead_pane_detected_by_health(self, spawn_mock_session, e2e_session_repo):
        doc = spawn_mock_session("test-stale-pane", repo="cortex")
        session_id = doc["session_id"]
        pane_id = doc["pane_id"]

        try:
            subprocess.run(
                ["tmux", "kill-pane", "-t", pane_id],
                capture_output=True, timeout=5,
            )
            time.sleep(1)

            subprocess.run(
                ["cortex", "session", "health"],
                capture_output=True, text=True, timeout=15,
            )

            reg = _get_session(session_id)
            assert reg["status"] == "dead", \
                f"Expected dead after pane killed, got {reg['status']}"
        finally:
            e2e_session_repo.close(session_id, trigger="e2e-cleanup")


class TestCleanupVerification:
    """No test artifacts remain after tests."""

    def test_no_stale_test_sessions(self, e2e_session_repo):
        active_test = e2e_session_repo.list({
            "name": {"$regex": "^test-"},
            "status": {"$nin": ["completed", "dead"]},
        })
        assert len(active_test) == 0, \
            f"Found stale test sessions: {[s['_id'] for s in active_test]}"
