"""Slice 2: Spatial spawn + layout E2E tests.

All tests use spawn_mock_session (no CC, no API calls).
"""
from __future__ import annotations

import json
import subprocess
import time

import pytest

pytestmark = [pytest.mark.slice2, pytest.mark.e2e]


def _get_session(session_id: str) -> dict:
    result = subprocess.run(
        ["cortex", "--json", "session", "get", session_id],
        capture_output=True, text=True, timeout=10,
    )
    return json.loads(result.stdout)


def _get_layout() -> dict:
    result = subprocess.run(
        ["cortex", "--json", "session", "layout"],
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


class TestLayout:
    """AC-2.1, AC-2.2: Layout command returns pane positions with session mapping."""

    def test_layout_returns_windows_and_panes(self, spawn_mock_session):
        doc = spawn_mock_session("test-layout-basic", repo="cortex")
        time.sleep(1)
        layout = _get_layout()

        assert "workspace" in layout
        assert "windows" in layout
        assert len(layout["windows"]) > 0

        pane = _find_pane_in_layout(layout, doc["pane_id"])
        assert pane is not None, f"Pane {doc['pane_id']} not found in layout"
        for field in ("left", "top", "width", "height"):
            assert field in pane, f"Missing field: {field}"
            assert isinstance(pane[field], int), f"{field} should be int"

    def test_layout_maps_session_names(self, spawn_mock_session):
        doc = spawn_mock_session("test-layout-mapped", repo="cortex")
        time.sleep(1)
        layout = _get_layout()

        pane = _find_pane_in_layout(layout, doc["pane_id"])
        assert pane is not None
        assert pane.get("session") == "test-layout-mapped", (
            f"Expected session 'test-layout-mapped', got {pane.get('session')}"
        )

    def test_layout_shows_untracked_panes(self):
        layout = _get_layout()
        all_panes = [p for w in layout["windows"] for p in w["panes"]]
        assert len(all_panes) > 0, "No panes found in layout"


class TestSpatialSpawn:
    """AC-2.3, AC-2.4: Spawn --beside and --below."""

    def test_spawn_beside_creates_horizontal_split(self, spawn_mock_session):
        first = spawn_mock_session("test-beside-anchor", repo="cortex")
        time.sleep(1)
        second = spawn_mock_session("test-beside-new", beside="test-beside-anchor")
        time.sleep(1)

        layout = _get_layout()
        p1 = _find_pane_in_layout(layout, first["pane_id"])
        p2 = _find_pane_in_layout(layout, second["pane_id"])

        assert p1 is not None and p2 is not None, "Both panes should be in layout"
        assert p1["top"] == p2["top"], (
            f"Horizontal split should have same top: {p1['top']} vs {p2['top']}"
        )
        assert p1["left"] != p2["left"], (
            "Horizontal split should have different left positions"
        )

    def test_spawn_below_creates_vertical_split(self, spawn_mock_session):
        first = spawn_mock_session("test-below-anchor", repo="cortex")
        time.sleep(1)
        second = spawn_mock_session("test-below-new", below="test-below-anchor")
        time.sleep(1)

        layout = _get_layout()
        p1 = _find_pane_in_layout(layout, first["pane_id"])
        p2 = _find_pane_in_layout(layout, second["pane_id"])

        assert p1 is not None and p2 is not None, "Both panes should be in layout"
        assert p1["left"] == p2["left"], (
            f"Vertical split should have same left: {p1['left']} vs {p2['left']}"
        )
        assert p1["top"] != p2["top"], (
            "Vertical split should have different top positions"
        )


class TestRefResolution:
    """AC-2.5: Spawn ref resolves by name, ID prefix, or pane_id."""

    def test_beside_resolves_by_name(self, spawn_mock_session):
        spawn_mock_session("test-ref-name", repo="cortex")
        time.sleep(1)
        second = spawn_mock_session("test-ref-name-split", beside="test-ref-name")
        assert second["pane_id"] is not None

    def test_beside_resolves_by_id_prefix(self, spawn_mock_session):
        first = spawn_mock_session("test-ref-prefix", repo="cortex")
        time.sleep(1)
        prefix = first["session_id"][:6]
        second = spawn_mock_session("test-ref-prefix-split", beside=prefix)
        assert second["pane_id"] is not None

    def test_beside_resolves_by_pane_id(self, spawn_mock_session):
        first = spawn_mock_session("test-ref-pane", repo="cortex")
        time.sleep(1)
        second = spawn_mock_session("test-ref-pane-split", beside=first["pane_id"])
        assert second["pane_id"] is not None


class TestColor:
    """AC-2.6: --color sets CC session color via /color."""

    def test_spawn_with_color_stores_in_registry(self, spawn_mock_session):
        doc = spawn_mock_session("test-color-blue", repo="cortex", color="blue")
        time.sleep(1)
        reg = _get_session(doc["session_id"])
        assert reg.get("color") == "blue", f"Expected color 'blue', got {reg.get('color')}"

class TestCleanupVerification:
    """No test artifacts remain."""

    def test_no_stale_test_sessions(self, e2e_session_repo):
        stale = e2e_session_repo.list({
            "name": {"$regex": "^test-"},
            "status": {"$nin": ["completed", "dead"]},
        })
        assert len(stale) == 0, (
            f"Found {len(stale)} stale test sessions: "
            f"{[s.get('name') for s in stale]}"
        )
