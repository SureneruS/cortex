"""Tests for Tier 2 hooks: SubagentStart, SubagentStop, TaskCreated, TaskCompleted, PostCompact.

All hooks are side-effect only (return {}), update the session registry via cortex CLI,
and skip silently when CORTEX_SESSION_ID is not set.
"""

from __future__ import annotations

import json
from unittest.mock import patch, MagicMock

import pytest

from nova.hooks.subagent_start import handle_subagent_start
from nova.hooks.subagent_stop import handle_subagent_stop
from nova.hooks.task_created import handle_task_created
from nova.hooks.task_completed import handle_task_completed
from nova.hooks.post_compact import handle_post_compact


@pytest.fixture(autouse=True)
def _set_cortex_session_id(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CORTEX_SESSION_ID", "test-session-123")


def _mock_cli_success() -> MagicMock:
    mock = MagicMock()
    mock.returncode = 0
    mock.stdout = "{}"
    return mock


# --- No context injection ---

class TestNoContextInjection:
    def test_subagent_start_returns_empty(self):
        with patch("nova.hooks.subagent_start.subprocess.run", return_value=_mock_cli_success()):
            result = handle_subagent_start({"agent_type": "Explore"})
        assert result == {}

    def test_subagent_stop_returns_empty(self):
        with patch("nova.hooks.subagent_stop.subprocess.run", return_value=_mock_cli_success()):
            result = handle_subagent_stop({"agent_type": "Explore"})
        assert result == {}

    def test_task_created_returns_empty(self):
        with patch("nova.hooks.task_created.subprocess.run", return_value=_mock_cli_success()):
            result = handle_task_created({"task": {"subject": "Fix bug"}, "total_tasks": 3})
        assert result == {}

    def test_task_completed_returns_empty(self):
        with patch("nova.hooks.task_completed.subprocess.run", return_value=_mock_cli_success()):
            result = handle_task_completed({"total_tasks": 3, "completed_tasks": 1})
        assert result == {}

    def test_post_compact_returns_empty(self):
        with patch("nova.hooks.post_compact.subprocess.run", return_value=_mock_cli_success()):
            result = handle_post_compact({})
        assert result == {}


# --- CORTEX_SESSION_ID guard ---

class TestSessionIdGuard:
    def test_subagent_start_skips_without_session_id(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("CORTEX_SESSION_ID")
        with patch("nova.hooks.subagent_start.subprocess.run") as mock_run:
            result = handle_subagent_start({"agent_type": "Explore"})
        assert result == {}
        mock_run.assert_not_called()

    def test_subagent_stop_skips_without_session_id(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("CORTEX_SESSION_ID")
        with patch("nova.hooks.subagent_stop.subprocess.run") as mock_run:
            result = handle_subagent_stop({"agent_type": "Explore"})
        assert result == {}
        mock_run.assert_not_called()

    def test_task_created_skips_without_session_id(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("CORTEX_SESSION_ID")
        with patch("nova.hooks.task_created.subprocess.run") as mock_run:
            result = handle_task_created({"task": {"subject": "Fix bug"}})
        assert result == {}
        mock_run.assert_not_called()

    def test_task_completed_skips_without_session_id(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("CORTEX_SESSION_ID")
        with patch("nova.hooks.task_completed.subprocess.run") as mock_run:
            result = handle_task_completed({"total_tasks": 3, "completed_tasks": 1})
        assert result == {}
        mock_run.assert_not_called()

    def test_post_compact_skips_without_session_id(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("CORTEX_SESSION_ID")
        with patch("nova.hooks.post_compact.subprocess.run") as mock_run:
            result = handle_post_compact({})
        assert result == {}
        mock_run.assert_not_called()


# --- Registry updates ---

class TestRegistryUpdates:
    def test_subagent_start_increments_count(self):
        with patch("nova.hooks.subagent_start.subprocess.run", return_value=_mock_cli_success()) as mock_run:
            handle_subagent_start({"agent_type": "Explore"})

        args = mock_run.call_args[0][0]
        assert args[0] == "cortex"
        assert args[1:4] == ["--json", "session", "update"]
        assert args[4] == "test-session-123"
        assert "--increment" in args
        assert args[args.index("--increment") + 1] == "subagent_count"
        assert "--trigger" in args
        assert args[args.index("--trigger") + 1] == "subagent_start"

        data_idx = args.index("--data") + 1
        data = json.loads(args[data_idx])
        assert data["last_subagent"]["type"] == "Explore"
        assert "started_at" in data["last_subagent"]

    def test_subagent_stop_stores_completion(self):
        with patch("nova.hooks.subagent_stop.subprocess.run", return_value=_mock_cli_success()) as mock_run:
            handle_subagent_stop({"agent_type": "general-purpose"})

        args = mock_run.call_args[0][0]
        assert args[1:4] == ["--json", "session", "update"]
        assert "--trigger" in args
        assert args[args.index("--trigger") + 1] == "subagent_stop"

        data_idx = args.index("--data") + 1
        data = json.loads(args[data_idx])
        assert data["last_subagent"]["type"] == "general-purpose"
        assert "completed_at" in data["last_subagent"]

    def test_task_created_stores_subject_and_count(self):
        with patch("nova.hooks.task_created.subprocess.run", return_value=_mock_cli_success()) as mock_run:
            handle_task_created({"task": {"subject": "Implement feature X"}, "total_tasks": 5})

        args = mock_run.call_args[0][0]
        assert args[1:4] == ["--json", "session", "update"]
        assert args[args.index("--trigger") + 1] == "task_created"

        data_idx = args.index("--data") + 1
        data = json.loads(args[data_idx])
        assert data["last_task_subject"] == "Implement feature X"
        assert data["task_count"] == 5
        assert "last_task_at" in data

    def test_task_created_truncates_long_subject(self):
        long_subject = "x" * 300
        with patch("nova.hooks.task_created.subprocess.run", return_value=_mock_cli_success()) as mock_run:
            handle_task_created({"task": {"subject": long_subject}, "total_tasks": 1})

        args = mock_run.call_args[0][0]
        data = json.loads(args[args.index("--data") + 1])
        assert len(data["last_task_subject"]) == 200

    def test_task_completed_stores_counts(self):
        with patch("nova.hooks.task_completed.subprocess.run", return_value=_mock_cli_success()) as mock_run:
            handle_task_completed({"total_tasks": 5, "completed_tasks": 3})

        args = mock_run.call_args[0][0]
        assert args[args.index("--trigger") + 1] == "task_completed"

        data = json.loads(args[args.index("--data") + 1])
        assert data["task_count"] == 5
        assert data["tasks_completed"] == 3
        assert "last_task_completed_at" in data

    def test_post_compact_increments_count(self):
        with patch("nova.hooks.post_compact.subprocess.run", return_value=_mock_cli_success()) as mock_run:
            handle_post_compact({})

        args = mock_run.call_args[0][0]
        assert args[1:4] == ["--json", "session", "update"]
        assert args[args.index("--trigger") + 1] == "post_compact"
        assert args[args.index("--increment") + 1] == "compact_count"

        data = json.loads(args[args.index("--data") + 1])
        assert "last_compaction_completed" in data
