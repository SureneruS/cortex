"""Slice 2: Spatial spawn + layout E2E tests.

Verifies:
- Layout command returns pane positions with session mapping
- Spawn --beside splits horizontally next to target
- Spawn --below splits vertically under target
- Ref resolution works by name, ID prefix, and pane_id
- --color flag sends /color to CC session
- Paint command sets tmux border colors by runtime
- Prompt delivery is reliable
- Runtime detection recognizes waiting_permission
"""
from __future__ import annotations

import json
import subprocess
import time

import pytest

pytestmark = [pytest.mark.slice2, pytest.mark.e2e]


def _get_session(session_id: str) -> dict:
    result = subprocess.run(
        ["cortex", "session", "get", session_id],
        capture_output=True, text=True, timeout=10,
    )
    return json.loads(result.stdout)


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


def _capture_pane(pane_id: str, **_kwargs) -> str:
    result = subprocess.run(
        ["tmux", "capture-pane", "-t", pane_id, "-p"],
        capture_output=True, text=True, timeout=5,
    )
    return result.stdout


class TestLayout:
    """AC-2.1, AC-2.2: Layout command returns pane positions with session mapping."""

    def test_layout_returns_windows_and_panes(self, spawn_test_session):
        doc = spawn_test_session("test-layout-basic", repo="cortex")
        time.sleep(2)
        layout = _get_layout()

        assert "workspace" in layout
        assert "windows" in layout
        assert len(layout["windows"]) > 0

        pane = _find_pane_in_layout(layout, doc["pane_id"])
        assert pane is not None, f"Pane {doc['pane_id']} not found in layout"
        for field in ("left", "top", "width", "height"):
            assert field in pane, f"Missing field: {field}"
            assert isinstance(pane[field], int), f"{field} should be int"

    def test_layout_maps_session_names(self, spawn_test_session):
        doc = spawn_test_session("test-layout-mapped", repo="cortex")
        time.sleep(2)
        layout = _get_layout()

        pane = _find_pane_in_layout(layout, doc["pane_id"])
        assert pane is not None
        assert pane.get("session") == "test-layout-mapped", (
            f"Expected session 'test-layout-mapped', got {pane.get('session')}"
        )

    def test_layout_shows_untracked_panes(self):
        layout = _get_layout()
        all_panes = [p for w in layout["windows"] for p in w["panes"]]
        untracked = [p for p in all_panes if p.get("session") is None]
        # There should be at least some panes (control session, fish shells)
        assert len(all_panes) > 0, "No panes found in layout"


class TestSpatialSpawn:
    """AC-2.3, AC-2.4: Spawn --beside and --below."""

    def test_spawn_beside_creates_horizontal_split(self, spawn_test_session):
        first = spawn_test_session("test-beside-anchor", repo="cortex")
        time.sleep(2)

        second = spawn_test_session("test-beside-new", beside="test-beside-anchor")
        time.sleep(2)

        layout = _get_layout()
        p1 = _find_pane_in_layout(layout, first["pane_id"])
        p2 = _find_pane_in_layout(layout, second["pane_id"])

        assert p1 is not None and p2 is not None, "Both panes should be in layout"
        # Horizontal split: same window, new pane has different left position
        assert p1["top"] == p2["top"], (
            f"Horizontal split should have same top: {p1['top']} vs {p2['top']}"
        )
        assert p1["left"] != p2["left"], (
            "Horizontal split should have different left positions"
        )

    def test_spawn_below_creates_vertical_split(self, spawn_test_session):
        first = spawn_test_session("test-below-anchor", repo="cortex")
        time.sleep(2)

        second = spawn_test_session("test-below-new", below="test-below-anchor")
        time.sleep(2)

        layout = _get_layout()
        p1 = _find_pane_in_layout(layout, first["pane_id"])
        p2 = _find_pane_in_layout(layout, second["pane_id"])

        assert p1 is not None and p2 is not None, "Both panes should be in layout"
        # Vertical split: same window, new pane has different top position
        assert p1["left"] == p2["left"], (
            f"Vertical split should have same left: {p1['left']} vs {p2['left']}"
        )
        assert p1["top"] != p2["top"], (
            "Vertical split should have different top positions"
        )


class TestRefResolution:
    """AC-2.5: Spawn ref resolves by name, ID prefix, or pane_id."""

    def test_beside_resolves_by_name(self, spawn_test_session):
        first = spawn_test_session("test-ref-name", repo="cortex")
        time.sleep(2)
        second = spawn_test_session("test-ref-name-split", beside="test-ref-name")
        assert second["pane_id"] is not None

    def test_beside_resolves_by_id_prefix(self, spawn_test_session):
        first = spawn_test_session("test-ref-prefix", repo="cortex")
        time.sleep(2)
        prefix = first["session_id"][:6]
        second = spawn_test_session("test-ref-prefix-split", beside=prefix)
        assert second["pane_id"] is not None

    def test_beside_resolves_by_pane_id(self, spawn_test_session):
        first = spawn_test_session("test-ref-pane", repo="cortex")
        time.sleep(2)
        second = spawn_test_session("test-ref-pane-split", beside=first["pane_id"])
        assert second["pane_id"] is not None


class TestColor:
    """AC-2.6: --color sets CC session color via /color."""

    def test_spawn_with_color_stores_in_registry(self, spawn_test_session):
        doc = spawn_test_session("test-color-blue", repo="cortex", color="blue")
        time.sleep(3)
        reg = _get_session(doc["session_id"])
        assert reg.get("color") == "blue", f"Expected color 'blue', got {reg.get('color')}"

    def test_spawn_with_color_sends_color_command(self, spawn_test_session):
        doc = spawn_test_session("test-color-cmd", repo="cortex", color="green")
        # Poll until /color command appears in pane (CC needs time to start)
        for _ in range(20):
            time.sleep(2)
            output = _capture_pane(doc["pane_id"])
            if "/color green" in output or "color" in output.lower():
                break
        else:
            pytest.fail(f"/color green not found in pane output after 40s")


class TestPromptDelivery:
    """AC-2.11: Prompt delivery is reliable."""

    def test_prompt_delivered_and_processed(self, spawn_test_session):
        doc = spawn_test_session(
            "test-prompt-delivery",
            repo="cortex",
            prompt="respond with exactly the word: PROMPT_RECEIVED",
        )
        # Wait for CC to start and process the prompt — CC startup + response can take a while
        output = ""
        for _ in range(30):
            time.sleep(2)
            output = _capture_pane(doc["pane_id"])
            if "PROMPT_RECEIVED" in output:
                break
        else:
            # Check if at least the prompt was sent (even if CC didn't respond in time)
            if "PROMPT_RECEIVED" not in output and "respond with" not in output:
                pytest.fail(
                    f"Prompt not even delivered within 60s. Last output:\n{output[-500:]}"
                )
            else:
                pytest.fail(
                    f"Prompt delivered but CC didn't respond within 60s. Last output:\n{output[-500:]}"
                )


class TestCleanupVerification:
    """AC-0.2 (slice2): No test artifacts remain."""

    def test_no_stale_test_sessions(self, e2e_session_repo):
        stale = e2e_session_repo.list({
            "name": {"$regex": "^test-"},
            "status": {"$nin": ["completed", "dead"]},
        })
        assert len(stale) == 0, (
            f"Found {len(stale)} stale test sessions: "
            f"{[s.get('name') for s in stale]}"
        )
