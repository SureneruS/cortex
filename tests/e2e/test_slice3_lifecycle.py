"""Slice 3: Session lifecycle E2E tests.

All tests use spawn_mock_session (no CC, no API calls).
Tests that required real CC (resume, restart, cc_version) have been removed —
those test CC integration, not cortex logic.
"""
from __future__ import annotations

import json
import subprocess
import time

import pytest

pytestmark = [pytest.mark.slice3, pytest.mark.e2e]


def _get_session(session_id: str) -> dict:
    result = subprocess.run(
        ["cortex", "session", "get", session_id],
        capture_output=True, text=True, timeout=10,
    )
    return json.loads(result.stdout)


def _pane_exists(pane_id: str) -> bool:
    result = subprocess.run(
        ["tmux", "capture-pane", "-t", pane_id, "-p"],
        capture_output=True, text=True,
    )
    return result.returncode == 0


def _pane_session_name(pane_id: str) -> str:
    result = subprocess.run(
        ["tmux", "display-message", "-t", pane_id, "-p", "#{session_name}"],
        capture_output=True, text=True, timeout=5,
    )
    return result.stdout.strip()


class TestPause:
    """Pause command. Uses mock sessions."""

    def test_pause_sends_exit_and_marks_paused(self, spawn_mock_session):
        doc = spawn_mock_session("test-pause-basic", repo="cortex")
        time.sleep(1)

        result = subprocess.run(
            ["cortex", "session", "pause", doc["session_id"]],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, f"Pause failed: {result.stderr}"

        reg = _get_session(doc["session_id"])
        assert reg["status"] == "paused", f"Expected paused, got {reg['status']}"
        assert not _pane_exists(doc["pane_id"]), "Pane should be dead after pause"

    def test_pause_fails_on_dead_pane(self, spawn_mock_session):
        doc = spawn_mock_session("test-pause-dead", repo="cortex")
        time.sleep(1)
        subprocess.run(["tmux", "kill-pane", "-t", doc["pane_id"]], capture_output=True)
        time.sleep(1)

        result = subprocess.run(
            ["cortex", "session", "pause", doc["session_id"]],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode != 0, "Pause should fail on dead pane"


class TestHideShow:
    """Hide and Show commands. Uses mock sessions."""

    def test_hide_moves_to_background(self, spawn_mock_session):
        doc = spawn_mock_session("test-hide-basic", repo="cortex")
        time.sleep(1)

        result = subprocess.run(
            ["cortex", "session", "hide", doc["session_id"]],
            capture_output=True, text=True, timeout=15,
        )
        assert result.returncode == 0, f"Hide failed: {result.stderr}"

        reg = _get_session(doc["session_id"])
        assert reg["status"] == "hidden", f"Expected hidden, got {reg['status']}"

        new_pane_id = reg.get("pane_id")
        assert new_pane_id is not None
        assert _pane_exists(new_pane_id), "Pane should still be alive in background"

        ws = _pane_session_name(new_pane_id)
        assert ws == "background", f"Pane should be in background workspace, got {ws}"

    def test_show_brings_back(self, spawn_mock_session):
        doc = spawn_mock_session("test-show-basic", repo="cortex")
        time.sleep(1)

        subprocess.run(
            ["cortex", "session", "hide", doc["session_id"]],
            capture_output=True, text=True, timeout=15,
        )

        result = subprocess.run(
            ["cortex", "session", "show", doc["session_id"]],
            capture_output=True, text=True, timeout=15,
        )
        assert result.returncode == 0, f"Show failed: {result.stderr}"

        reg = _get_session(doc["session_id"])
        assert reg["status"] == "active", f"Expected active, got {reg['status']}"

        new_pane_id = reg.get("pane_id")
        assert _pane_exists(new_pane_id), "Pane should be alive"

        ws = _pane_session_name(new_pane_id)
        assert ws == "work", f"Pane should be in work workspace, got {ws}"

    def test_hide_show_roundtrip(self, spawn_mock_session):
        doc = spawn_mock_session("test-roundtrip", repo="cortex")
        time.sleep(1)

        subprocess.run(
            ["cortex", "session", "hide", doc["session_id"]],
            capture_output=True, text=True, timeout=15,
        )
        subprocess.run(
            ["cortex", "session", "show", doc["session_id"]],
            capture_output=True, text=True, timeout=15,
        )

        reg = _get_session(doc["session_id"])
        new_pane_id = reg.get("pane_id")
        assert _pane_exists(new_pane_id), "Pane should be alive after roundtrip"


class TestResumeFailsIfActive:
    """Resume on active session should fail."""

    def test_resume_fails_if_active(self, spawn_mock_session):
        doc = spawn_mock_session("test-resume-active", repo="cortex")
        time.sleep(1)

        result = subprocess.run(
            ["cortex", "session", "resume", doc["session_id"]],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode != 0, "Resume should fail on active session"


class TestCleanupVerification:
    """No test artifacts remain."""

    def test_no_stale_test_sessions(self, e2e_session_repo):
        stale = e2e_session_repo.list({
            "name": {"$regex": "^test-"},
            "status": {"$nin": ["completed", "dead", "paused"]},
        })
        assert len(stale) == 0, (
            f"Found {len(stale)} stale test sessions: "
            f"{[s.get('name') for s in stale]}"
        )
