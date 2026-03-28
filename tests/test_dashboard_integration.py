from __future__ import annotations

import asyncio
import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient

_real_sleep = asyncio.sleep


class TestBlueprintLifecycle:
    def test_blueprint_to_resolved_lifecycle(self, api_client: TestClient):
        bp = {"title": "Weekly", "sections": [{"id": "s1", "type": "text", "content": "hello"}]}
        api_client.post("/api/dashboard/blueprint", json=bp)

        resp = api_client.get("/api/dashboard/resolved")
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Weekly"
        assert data["sections"][0]["id"] == "s1"
        assert "resolved_at" in data

    def test_blueprint_overwrite(self, api_client: TestClient):
        bp1 = {"title": "First", "sections": []}
        bp2 = {"title": "Second", "sections": []}
        api_client.post("/api/dashboard/blueprint", json=bp1)
        api_client.post("/api/dashboard/blueprint", json=bp2)

        resp = api_client.get("/api/dashboard/blueprint")
        assert resp.status_code == 200
        assert resp.json()["blueprint"]["title"] == "Second"

        resp = api_client.get("/api/dashboard/snapshots")
        snapshots = resp.json()
        blueprint_snapshots = [s for s in snapshots if s["snapshot_type"] == "blueprint"]
        assert len(blueprint_snapshots) == 2
        titles = {s["data"]["title"] for s in blueprint_snapshots}
        assert titles == {"First", "Second"}

    def test_resolved_404_no_blueprint(self, api_client: TestClient):
        resp = api_client.get("/api/dashboard/resolved")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "No blueprint"


class TestWatcherResolve:
    @pytest.mark.anyio
    async def test_watcher_resolves_source(self, async_client: AsyncClient):
        source_data = {"count": 42, "label": "open PRs"}
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(source_data)

        bp = {
            "title": "Dash",
            "sections": [{"id": "prs", "type": "table", "source": {"command": "echo test", "interval": 60}}],
        }

        with patch("cortex.dashboard.subprocess.run", return_value=mock_result), \
             patch("cortex.dashboard.asyncio.sleep", side_effect=asyncio.CancelledError):
            resp = await async_client.post("/api/dashboard/blueprint", json=bp)
            assert resp.status_code == 201
            await _real_sleep(0.1)

        resp = await async_client.get("/api/dashboard/resolved")
        assert resp.status_code == 200
        data = resp.json()
        section = data["sections"][0]
        assert section["_resolved"] == source_data
        assert section["_status"] == "ok"

    @pytest.mark.anyio
    async def test_watcher_error_sets_status(self, async_client: AsyncClient):
        bp = {
            "title": "Dash",
            "sections": [{"id": "failing", "type": "table", "source": {"command": "timeout cmd", "interval": 60}}],
        }

        with patch(
            "cortex.dashboard.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="timeout cmd", timeout=30),
        ), patch("cortex.dashboard.asyncio.sleep", side_effect=asyncio.CancelledError):
            resp = await async_client.post("/api/dashboard/blueprint", json=bp)
            assert resp.status_code == 201
            await _real_sleep(0.1)

        resp = await async_client.get("/api/dashboard/resolved")
        assert resp.status_code == 200
        section = resp.json()["sections"][0]
        assert section["_status"] == "error"

    @pytest.mark.anyio
    async def test_watcher_transform_pr_table_rows(self, async_client: AsyncClient):
        pr_data = [
            {"number": 101, "title": "feat(ATS-100): Add feature", "isDraft": False, "reviewDecision": "APPROVED"},
            {"number": 102, "title": "fix(ATS-200): Bug fix", "isDraft": True, "reviewDecision": ""},
        ]
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(pr_data)

        bp = {
            "title": "PR Dash",
            "sections": [
                {
                    "id": "pr-table",
                    "type": "table",
                    "source": {"command": "gh pr list", "transform": "pr_table_rows", "interval": 60},
                }
            ],
        }

        with patch("cortex.dashboard.subprocess.run", return_value=mock_result), \
             patch("cortex.dashboard.asyncio.sleep", side_effect=asyncio.CancelledError):
            resp = await async_client.post("/api/dashboard/blueprint", json=bp)
            assert resp.status_code == 201
            await _real_sleep(0.1)

        resp = await async_client.get("/api/dashboard/resolved")
        assert resp.status_code == 200
        rows = resp.json()["sections"][0]["_resolved"]
        assert len(rows) == 2
        assert rows[0][0] == {"text": "#101", "url": "https://github.com/cercli/recruitment-backend/pull/101"}
        assert rows[0][1] == {"text": "ATS-100", "url": "https://linear.app/cercli/issue/ATS-100"}
        assert rows[0][2] == {"text": "Ready", "color": "green"}
        assert rows[0][4] == {"text": "Approved", "color": "green"}
        assert rows[1][2] == {"text": "Draft", "color": "muted"}

    @pytest.mark.anyio
    async def test_watcher_cancelled_on_new_blueprint(self, async_client: AsyncClient):
        from cortex import dashboard

        bp1 = {
            "title": "Old",
            "sections": [{"id": "s1", "type": "text", "source": {"command": "echo old", "interval": 60}}],
        }
        bp2 = {
            "title": "New",
            "sections": [{"id": "s2", "type": "text", "content": "static"}],
        }

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = '{"x":1}'

        with patch("cortex.dashboard.subprocess.run", return_value=mock_result), \
             patch("cortex.dashboard.asyncio.sleep", side_effect=asyncio.CancelledError):
            await async_client.post("/api/dashboard/blueprint", json=bp1)
            await _real_sleep(0.05)
            task1 = dashboard._watcher_task

            await async_client.post("/api/dashboard/blueprint", json=bp2)
            await _real_sleep(0.05)

        assert task1 is not None
        assert task1.cancelled() or task1.done()


class TestCheckpointQuery:
    def test_checkpoint_query(self, state, api_client: TestClient):
        state.save_checkpoint("2026-03-09", "Week 11 summary", stream_ids=["stream-1"])

        resp = api_client.get("/api/dashboard/checkpoints", params={"week_of": "2026-03-09"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["week_of"] == "2026-03-09"
        assert data["content"] == "Week 11 summary"
        assert data["stream_ids"] == ["stream-1"]
        assert "created_at" in data
