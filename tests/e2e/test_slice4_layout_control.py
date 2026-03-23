"""Slice 4: Layout control E2E tests.

All tests use spawn_mock_session (no CC, no API calls).
"""
from __future__ import annotations

import json
import subprocess
import time

import pytest

pytestmark = [pytest.mark.slice4, pytest.mark.e2e]


def _get_layout() -> dict:
    result = subprocess.run(
        ["cortex", "session", "layout"],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, f"layout failed: {result.stderr}"
    return json.loads(result.stdout)


def _find_pane_in_layout(layout: dict, pane_id: str) -> dict | None:
    for window in layout.get("windows", []):
        for pane in window.get("panes", []):
            if pane["pane_id"] == pane_id:
                return pane
    return None


def _panes_in_same_window(layout: dict, pane_id_a: str, pane_id_b: str) -> bool:
    for window in layout.get("windows", []):
        pane_ids = {p["pane_id"] for p in window["panes"]}
        if pane_id_a in pane_ids and pane_id_b in pane_ids:
            return True
    return False


def _pane_window_id(layout: dict, pane_id: str) -> str | None:
    for window in layout.get("windows", []):
        for pane in window["panes"]:
            if pane["pane_id"] == pane_id:
                return window["id"]
    return None


class TestGather:
    """Gather sessions into a single window."""

    def test_gather_merges_panes(self, spawn_mock_session):
        a = spawn_mock_session("test-gather-a", repo="cortex")
        b = spawn_mock_session("test-gather-b", repo="cortex")
        c = spawn_mock_session("test-gather-c", repo="cortex")
        time.sleep(1)

        # They start in separate windows
        layout = _get_layout()
        assert not _panes_in_same_window(layout, a["pane_id"], b["pane_id"])

        result = subprocess.run(
            ["cortex", "session", "gather", "test-gather-a", "test-gather-b", "test-gather-c"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0, f"Gather failed: {result.stderr}"

        layout = _get_layout()
        assert _panes_in_same_window(layout, a["pane_id"], b["pane_id"]), "a and b should be in same window"
        assert _panes_in_same_window(layout, a["pane_id"], c["pane_id"]), "a and c should be in same window"

    def test_gather_applies_layout(self, spawn_mock_session):
        a = spawn_mock_session("test-gather-layout-a", repo="cortex")
        b = spawn_mock_session("test-gather-layout-b", repo="cortex")
        time.sleep(1)

        result = subprocess.run(
            ["cortex", "session", "gather", "test-gather-layout-a", "test-gather-layout-b", "--layout", "even-horizontal"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output["layout"] == "even-horizontal"

    def test_gather_needs_at_least_two(self, spawn_mock_session):
        spawn_mock_session("test-gather-solo", repo="cortex")
        time.sleep(1)

        result = subprocess.run(
            ["cortex", "session", "gather", "test-gather-solo"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode != 0, "Gather should fail with only 1 session"


class TestScatter:
    """Break sessions into separate windows."""

    def test_scatter_separates_panes(self, spawn_mock_session):
        a = spawn_mock_session("test-scatter-a", repo="cortex")
        time.sleep(1)
        b = spawn_mock_session("test-scatter-b", beside="test-scatter-a")
        time.sleep(1)

        # They start in same window
        layout = _get_layout()
        assert _panes_in_same_window(layout, a["pane_id"], b["pane_id"])

        result = subprocess.run(
            ["cortex", "session", "scatter", "test-scatter-a", "test-scatter-b"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0, f"Scatter failed: {result.stderr}"

        layout = _get_layout()
        assert not _panes_in_same_window(layout, a["pane_id"], b["pane_id"]), "Panes should be in separate windows"


class TestMove:
    """Move a session beside or below another."""

    def test_move_beside(self, spawn_mock_session):
        a = spawn_mock_session("test-move-a", repo="cortex")
        b = spawn_mock_session("test-move-b", repo="cortex")
        time.sleep(1)

        # Start in separate windows
        layout = _get_layout()
        assert not _panes_in_same_window(layout, a["pane_id"], b["pane_id"])

        result = subprocess.run(
            ["cortex", "session", "move", "test-move-b", "--beside", "test-move-a"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0, f"Move failed: {result.stderr}"

        layout = _get_layout()
        assert _panes_in_same_window(layout, a["pane_id"], b["pane_id"]), "b should be beside a"

    def test_move_below(self, spawn_mock_session):
        a = spawn_mock_session("test-move-below-a", repo="cortex")
        b = spawn_mock_session("test-move-below-b", repo="cortex")
        time.sleep(1)

        result = subprocess.run(
            ["cortex", "session", "move", "test-move-below-b", "--below", "test-move-below-a"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0

        layout = _get_layout()
        pa = _find_pane_in_layout(layout, a["pane_id"])
        pb = _find_pane_in_layout(layout, b["pane_id"])
        assert pa is not None and pb is not None
        assert pa["left"] == pb["left"], "Vertical: same left"
        assert pa["top"] != pb["top"], "Vertical: different top"

    def test_move_requires_target(self, spawn_mock_session):
        spawn_mock_session("test-move-no-target", repo="cortex")
        time.sleep(1)

        result = subprocess.run(
            ["cortex", "session", "move", "test-move-no-target"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode != 0, "Move should fail without --beside or --below"


class TestGatherScatterRoundtrip:
    """Gather then scatter returns to separate windows."""

    def test_roundtrip(self, spawn_mock_session):
        a = spawn_mock_session("test-rt-a", repo="cortex")
        b = spawn_mock_session("test-rt-b", repo="cortex")
        time.sleep(1)

        subprocess.run(
            ["cortex", "session", "gather", "test-rt-a", "test-rt-b"],
            capture_output=True, text=True, timeout=10,
        )
        layout = _get_layout()
        assert _panes_in_same_window(layout, a["pane_id"], b["pane_id"])

        subprocess.run(
            ["cortex", "session", "scatter", "test-rt-a", "test-rt-b"],
            capture_output=True, text=True, timeout=10,
        )
        layout = _get_layout()
        assert not _panes_in_same_window(layout, a["pane_id"], b["pane_id"])


class TestCleanupVerification:
    def test_no_stale_test_sessions(self, e2e_session_repo):
        stale = e2e_session_repo.list({
            "name": {"$regex": "^test-"},
            "status": {"$nin": ["completed", "dead", "paused"]},
        })
        assert len(stale) == 0, (
            f"Found {len(stale)} stale test sessions: "
            f"{[s.get('name') for s in stale]}"
        )
