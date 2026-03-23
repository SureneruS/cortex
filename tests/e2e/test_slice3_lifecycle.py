"""Slice 3: Session lifecycle E2E tests.

Most tests use spawn_mock_session (no CC, no API calls).
Only resume and conversation roundtrip tests use real CC.
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


def _capture_pane(pane_id: str) -> str:
    result = subprocess.run(
        ["tmux", "capture-pane", "-t", pane_id, "-p"],
        capture_output=True, text=True, timeout=5,
    )
    return result.stdout


def _pane_session_name(pane_id: str) -> str:
    result = subprocess.run(
        ["tmux", "display-message", "-t", pane_id, "-p", "#{session_name}"],
        capture_output=True, text=True, timeout=5,
    )
    return result.stdout.strip()


class TestPause:
    """AC-3.1, AC-3.2, AC-3.3: Pause command. Uses mock sessions."""

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

    def test_pause_preserves_cc_session_id(self, spawn_test_session):
        """Needs real CC so SessionStart hook sets cc_session_id."""
        doc = spawn_test_session("test-pause-ccid", repo="cortex")
        time.sleep(3)

        for _ in range(10):
            reg = _get_session(doc["session_id"])
            if reg.get("cc_session_id"):
                break
            time.sleep(1)

        subprocess.run(
            ["cortex", "session", "pause", doc["session_id"]],
            capture_output=True, text=True, timeout=30,
        )
        reg = _get_session(doc["session_id"])
        assert reg.get("cc_session_id") is not None, "cc_session_id should be preserved after pause"

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


class TestResume:
    """AC-3.4, AC-3.5, AC-3.6: Resume command."""

    def test_resume_restores_paused_session(self, spawn_test_session):
        """Needs real CC for --resume to work."""
        doc = spawn_test_session("test-resume-basic", repo="cortex")
        time.sleep(3)

        for _ in range(10):
            reg = _get_session(doc["session_id"])
            if reg.get("cc_session_id"):
                break
            time.sleep(1)

        subprocess.run(
            ["cortex", "session", "pause", doc["session_id"]],
            capture_output=True, text=True, timeout=30,
        )

        result = subprocess.run(
            ["cortex", "session", "resume", doc["session_id"]],
            capture_output=True, text=True, timeout=15,
        )
        assert result.returncode == 0, f"Resume failed: {result.stderr}"

        reg = _get_session(doc["session_id"])
        assert reg["status"] == "active", f"Expected active, got {reg['status']}"
        assert reg.get("pane_id") is not None, "Should have a new pane_id"
        assert _pane_exists(reg["pane_id"]), "New pane should be alive"

    def test_resume_restores_repo_and_color(self, spawn_test_session):
        """Needs real CC for --resume to work."""
        doc = spawn_test_session("test-resume-meta", repo="cortex", color="purple")
        time.sleep(3)

        for _ in range(10):
            reg = _get_session(doc["session_id"])
            if reg.get("cc_session_id"):
                break
            time.sleep(1)

        subprocess.run(
            ["cortex", "session", "pause", doc["session_id"]],
            capture_output=True, text=True, timeout=30,
        )

        result = subprocess.run(
            ["cortex", "session", "resume", doc["session_id"]],
            capture_output=True, text=True, timeout=15,
        )
        assert result.returncode == 0

        reg = _get_session(doc["session_id"])
        assert reg.get("repos") == ["cortex"], f"Repo not restored: {reg.get('repos')}"
        assert reg.get("color") == "purple", f"Color not restored: {reg.get('color')}"

    def test_resume_fails_if_active(self, spawn_mock_session):
        doc = spawn_mock_session("test-resume-active", repo="cortex")
        time.sleep(1)

        result = subprocess.run(
            ["cortex", "session", "resume", doc["session_id"]],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode != 0, "Resume should fail on active session"


class TestHideShow:
    """AC-3.7, AC-3.8, AC-3.9: Hide and Show commands. Uses mock sessions."""

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

        output = _capture_pane(new_pane_id)
        assert len(output.strip()) > 0, "Pane should have content"


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
