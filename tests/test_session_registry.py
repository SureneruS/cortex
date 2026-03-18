from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner
from pymongo import MongoClient

from cortex.cli import cli
from cortex.session_registry import MongoSessionRepo


@pytest.fixture
def session_repo():
    client = MongoClient("mongodb://localhost:27017")
    db = client["cortex_test"]
    repo = MongoSessionRepo(db)
    yield repo
    db.drop_collection("session_registry")
    client.close()


def test_register_and_get(session_repo):
    doc = session_repo.register("sess-1", {"name": "fix-login", "goal": "Fix redirect loop"})
    assert doc["_id"] == "sess-1"
    assert doc["name"] == "fix-login"
    assert doc["status"] == "active"
    assert doc["runtime"] == "unknown"
    assert "created_at" in doc
    assert len(doc["events"]) == 1
    assert doc["events"][0]["field"] == "status"
    assert doc["events"][0]["from"] is None
    assert doc["events"][0]["to"] == "active"
    assert doc["events"][0]["trigger"] == "spawn"

    fetched = session_repo.get("sess-1")
    assert fetched is not None
    assert fetched["name"] == "fix-login"


def test_register_generates_id(session_repo):
    doc = session_repo.register(None, {"name": "auto-id"})
    assert doc["_id"] is not None
    assert len(doc["_id"]) == 12


def test_get_nonexistent(session_repo):
    assert session_repo.get("nope") is None


def test_update_merges_fields(session_repo):
    session_repo.register("sess-1", {"name": "fix-login", "goal": "Fix redirect"})
    updated = session_repo.update("sess-1", {"status": "idle", "pane_id": 12})
    assert updated["status"] == "idle"
    assert updated["pane_id"] == 12
    assert updated["name"] == "fix-login"  # unchanged
    assert len(updated["events"]) == 2
    assert updated["events"][1]["field"] == "status"
    assert updated["events"][1]["from"] == "active"
    assert updated["events"][1]["to"] == "idle"


def test_update_nonexistent(session_repo):
    assert session_repo.update("nope", {"status": "idle"}) is None


def test_list_with_filters(session_repo):
    session_repo.register("s1", {"status": "active", "workspace": "default"})
    session_repo.register("s2", {"status": "active", "workspace": "background"})
    session_repo.register("s3", {"status": "completed"})

    active = session_repo.list({"status": "active"})
    assert len(active) == 2

    background = session_repo.list({"workspace": "background"})
    assert len(background) == 1
    assert background[0]["_id"] == "s2"


def test_list_all(session_repo):
    session_repo.register("s1", {"name": "a"})
    session_repo.register("s2", {"name": "b"})
    all_sessions = session_repo.list()
    assert len(all_sessions) == 2


def test_list_brief_excludes_events(session_repo):
    session_repo.register("s1", {"name": "a"})
    session_repo.update("s1", {"status": "idle"})
    results = session_repo.list(brief=True)
    assert len(results) == 1
    assert "events" not in results[0]
    assert results[0]["name"] == "a"


def test_list_brief_excludes_watch_last_state(session_repo):
    session_repo.register("s1", {"name": "watcher"})
    session_repo.update(
        "s1",
        {
            "status": "watching",
            "watch": {
                "type": "pr",
                "repo": "owner/repo",
                "number": 42,
                "last_state": {"comments": 5, "checks": "pass"},
            },
        },
    )
    results = session_repo.list(brief=True)
    assert "watch" in results[0]
    assert "last_state" not in results[0]["watch"]
    assert results[0]["watch"]["type"] == "pr"


def test_list_with_limit(session_repo):
    for i in range(5):
        session_repo.register(f"s{i}", {"name": f"session-{i}"})
    results = session_repo.list(limit=3)
    assert len(results) == 3


def test_list_limit_zero_returns_all(session_repo):
    for i in range(3):
        session_repo.register(f"s{i}", {"name": f"session-{i}"})
    results = session_repo.list(limit=0)
    assert len(results) == 3


def test_close_session(session_repo):
    session_repo.register("s1", {"name": "test"})
    closed = session_repo.close("s1")
    assert closed["status"] == "completed"
    assert "closed_at" in closed
    assert len(closed["events"]) == 2
    assert closed["events"][1]["field"] == "status"
    assert closed["events"][1]["to"] == "completed"
    assert closed["events"][1]["trigger"] == "close"


def test_query_by_array_element(session_repo):
    session_repo.register("s1", {"tools_used": ["Bash", "mcp__sentry__search_issues"]})
    session_repo.register("s2", {"tools_used": ["Bash", "Edit"]})

    results = session_repo.list({"tools_used": "mcp__sentry__search_issues"})
    assert len(results) == 1
    assert results[0]["_id"] == "s1"


def test_update_records_runtime_event(session_repo):
    session_repo.register("s1", {"name": "test"})
    updated = session_repo.update("s1", {"runtime": "working"}, trigger="health-check")
    assert updated["runtime"] == "working"
    assert len(updated["events"]) == 2
    evt = updated["events"][1]
    assert evt["field"] == "runtime"
    assert evt["from"] == "unknown"
    assert evt["to"] == "working"
    assert evt["trigger"] == "health-check"


def test_update_both_fields_records_two_events(session_repo):
    session_repo.register("s1", {"name": "test"})
    updated = session_repo.update("s1", {"status": "paused", "runtime": "waiting_input"})
    assert len(updated["events"]) == 3  # spawn + status + runtime


def test_update_no_event_when_unchanged(session_repo):
    session_repo.register("s1", {"name": "test"})
    updated = session_repo.update("s1", {"status": "active"})
    assert len(updated["events"]) == 1  # only the spawn event


def test_update_non_status_fields_no_events(session_repo):
    session_repo.register("s1", {"name": "test"})
    updated = session_repo.update("s1", {"pane_id": "%99", "current_task": "coding"})
    assert len(updated["events"]) == 1  # only the spawn event


def test_update_validates_status(session_repo):
    session_repo.register("s1", {"name": "test"})
    with pytest.raises(ValueError, match="Invalid status"):
        session_repo.update("s1", {"status": "bogus"})


def test_update_validates_runtime(session_repo):
    session_repo.register("s1", {"name": "test"})
    with pytest.raises(ValueError, match="Invalid runtime"):
        session_repo.update("s1", {"runtime": "bogus"})


def test_close_with_custom_trigger(session_repo):
    session_repo.register("s1", {"name": "test"})
    closed = session_repo.close("s1", trigger="auto-close")
    assert closed["events"][1]["trigger"] == "auto-close"


def test_update_runtime_convenience(session_repo):
    session_repo.register("s1", {"name": "test"})
    updated = session_repo.update_runtime("s1", "waiting_input")
    assert updated["runtime"] == "waiting_input"
    assert updated["events"][1]["trigger"] == "health-check"


def test_backward_compat_old_session(session_repo):
    """Old sessions without events/runtime still work with update."""
    session_repo._col.insert_one({"_id": "old-1", "status": "active", "name": "legacy"})
    updated = session_repo.update("old-1", {"status": "idle"})
    assert updated["status"] == "idle"
    assert len(updated["events"]) == 1
    assert updated["events"][0]["from"] == "active"
    assert updated["events"][0]["to"] == "idle"


# --- CLI tests ---


@pytest.fixture
def cli_db():
    client = MongoClient("mongodb://localhost:27017")
    db = client["cortex_test"]
    yield db
    db.drop_collection("session_registry")
    client.close()


@pytest.fixture
def _patch_cli_db(cli_db):
    """Route CLI's get_db() to the test database."""
    with patch("cortex.mongo.get_db", return_value=cli_db):
        yield


@pytest.fixture
def _seed_session(cli_db):
    """Seed a session directly in MongoDB for CLI tests."""
    repo = MongoSessionRepo(cli_db)
    repo.register("cli-test-1", {"name": "test-session", "goal": "Test CLI"})


def _run_cli(args: list[str]) -> tuple[int, dict | list]:
    runner = CliRunner()
    result = runner.invoke(cli, args)
    return result.exit_code, json.loads(result.output) if result.output.strip() else {}


class TestCLIUpdate:
    def test_update_merges_fields(self, _patch_cli_db, _seed_session):
        code, output = _run_cli(
            ["session", "update", "cli-test-1", "--data", '{"status":"idle","custom":"val"}']
        )
        assert code == 0
        assert output["status"] == "idle"
        assert output["custom"] == "val"
        assert output["name"] == "test-session"

    def test_update_nonexistent_session(self, _patch_cli_db):
        code, output = _run_cli(["session", "update", "nope", "--data", '{"status":"idle"}'])
        assert code == 1
        assert "not found" in output["error"]

    def test_update_invalid_json(self, _patch_cli_db, _seed_session):
        code, output = _run_cli(["session", "update", "cli-test-1", "--data", "not-json"])
        assert code == 1
        assert "Invalid JSON" in output["error"]


@pytest.fixture
def _mock_state():
    """Mock load_config + StateManager so close doesn't need real SQLite."""
    mock_state = MagicMock()
    mock_state.get_streams_for_session.return_value = []
    with (
        patch("cortex.cli.load_config"),
        patch("cortex.cli.StateManager", return_value=mock_state),
    ):
        yield mock_state


@pytest.fixture
def _seed_session_with_pane(cli_db):
    repo = MongoSessionRepo(cli_db)
    repo.register("cli-pane-1", {"name": "pane-session", "pane_id": "%42"})


class TestCLIClose:
    def test_close_session_no_pane(self, _patch_cli_db, _seed_session, _mock_state):
        code, output = _run_cli(["session", "close", "cli-test-1"])
        assert code == 0
        assert output["status"] == "completed"
        assert "closed_at" in output

    def test_close_nonexistent_session(self, _patch_cli_db, _mock_state):
        code, output = _run_cli(["session", "close", "nope"])
        assert code == 1
        assert "not found" in output["error"]

    def test_close_force_skips_memorize(self, _patch_cli_db, _seed_session_with_pane, _mock_state):
        with (
            patch("cortex.cli._pane_exists", return_value=True),
            patch("cortex.cli._send_to_pane") as send,
            patch("cortex.cli._kill_pane", return_value=True) as kill,
        ):
            code, output = _run_cli(["session", "close", "cli-pane-1", "--force"])
        assert code == 0
        assert output["status"] == "completed"
        send.assert_not_called()
        kill.assert_called_once_with("%42")

    def test_close_lifecycle_with_pane(self, _patch_cli_db, _seed_session_with_pane, _mock_state):
        with (
            patch("cortex.cli._pane_exists", return_value=True),
            patch("cortex.cli._send_to_pane", return_value=True) as send,
            patch("cortex.cli._wait_for_idle", return_value=True) as wait,
            patch("cortex.cli._kill_pane", return_value=True) as kill,
        ):
            code, output = _run_cli(["session", "close", "cli-pane-1"])
        assert code == 0
        assert output["status"] == "completed"
        send.assert_called_once_with("%42", "/memorize")
        wait.assert_called_once_with("%42", timeout=30)
        kill.assert_called_once_with("%42")

    def test_close_pane_gone_skips_terminal(
        self, _patch_cli_db, _seed_session_with_pane, _mock_state
    ):
        with (
            patch("cortex.cli._pane_exists", return_value=False),
            patch("cortex.cli._send_to_pane") as send,
            patch("cortex.cli._kill_pane") as kill,
        ):
            code, output = _run_cli(["session", "close", "cli-pane-1"])
        assert code == 0
        assert output["status"] == "completed"
        send.assert_not_called()
        kill.assert_not_called()

    def test_close_memorize_timeout_continues(
        self, _patch_cli_db, _seed_session_with_pane, _mock_state
    ):
        with (
            patch("cortex.cli._pane_exists", return_value=True),
            patch("cortex.cli._send_to_pane", return_value=True),
            patch("cortex.cli._wait_for_idle", return_value=False),
            patch("cortex.cli._kill_pane", return_value=True) as kill,
        ):
            code, output = _run_cli(["session", "close", "cli-pane-1"])
        assert code == 0
        assert output["status"] == "completed"
        kill.assert_called_once_with("%42")

    def test_close_updates_linked_stream(self, _patch_cli_db, _seed_session_with_pane, _mock_state):
        _mock_state.get_streams_for_session.return_value = ["stream-1"]
        with patch("cortex.cli._pane_exists", return_value=False):
            code, output = _run_cli(["session", "close", "cli-pane-1"])
        assert code == 0
        _mock_state.add_update.assert_called_once()
        call_args = _mock_state.add_update.call_args
        assert call_args[0][0] == "stream-1"
        assert "session_close" in str(call_args[1]["metadata"])


class TestCLIUpdateEvents:
    def test_update_with_trigger(self, _patch_cli_db, _seed_session, cli_db):
        code, output = _run_cli(
            [
                "session",
                "update",
                "cli-test-1",
                "--data",
                '{"status":"paused"}',
                "--trigger",
                "user-action",
            ]
        )
        assert code == 0
        assert output["status"] == "paused"
        doc = MongoSessionRepo(cli_db).get("cli-test-1")
        assert len(doc["events"]) == 2
        assert doc["events"][1]["trigger"] == "user-action"

    def test_update_invalid_status_returns_error(self, _patch_cli_db, _seed_session):
        code, output = _run_cli(["session", "update", "cli-test-1", "--data", '{"status":"bogus"}'])
        assert code == 1
        assert "Invalid status" in output["error"]


class TestCLIHealth:
    def test_health_persists_runtime_busy(self, _patch_cli_db, _seed_session_with_pane, cli_db):
        with (
            patch("cortex.cli._get_tmux_panes", return_value={"%42"}),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(
                returncode=0, stdout="Working on task...\n", stderr=""
            )
            code, output = _run_cli(["session", "health"])
        assert code == 0
        runtime_findings = [f for f in output["findings"] if f.get("check") == "runtime"]
        assert len(runtime_findings) == 1
        assert runtime_findings[0]["runtime"] == "working"
        doc = MongoSessionRepo(cli_db).get("cli-pane-1")
        assert doc["runtime"] == "working"
        runtime_events = [e for e in doc["events"] if e["field"] == "runtime"]
        assert len(runtime_events) == 1
        assert runtime_events[0]["to"] == "working"

    def test_health_dead_pane_updates_status(self, _patch_cli_db, _seed_session_with_pane, cli_db):
        with patch("cortex.cli._get_tmux_panes", return_value=set()):
            code, output = _run_cli(["session", "health"])
        assert code == 0
        dead_findings = [f for f in output["findings"] if f.get("check") == "dead_pane"]
        assert len(dead_findings) == 1
        assert dead_findings[0]["session_id"] == "cli-pane-1"
        assert output["summary"]["critical"] == 1
        doc = MongoSessionRepo(cli_db).get("cli-pane-1")
        assert doc["status"] == "dead"
        status_events = [e for e in doc["events"] if e["field"] == "status"]
        assert status_events[-1]["to"] == "dead"
        assert status_events[-1]["trigger"] == "health-check"

    def test_health_detects_stale_session(self, _patch_cli_db, cli_db):
        from datetime import datetime, timezone, timedelta

        repo = MongoSessionRepo(cli_db)
        old_time = (datetime.now(timezone.utc) - timedelta(hours=30)).isoformat()
        repo._col.insert_one({
            "_id": "stale-1",
            "name": "stale-session",
            "status": "active",
            "pane_id": "%99",
            "runtime": "unknown",
            "created_at": old_time,
            "events": [{"field": "status", "from": None, "to": "active", "at": old_time, "trigger": "spawn"}],
        })
        with (
            patch("cortex.cli._get_tmux_panes", return_value={"%99"}),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(returncode=0, stdout="❯ \n", stderr="")
            code, output = _run_cli(["session", "health"])
        assert code == 0
        stale = [f for f in output["findings"] if f.get("check") == "stale"]
        assert len(stale) == 1
        assert stale[0]["hours_since_activity"] > 24

    def test_health_detects_untracked_panes(self, _patch_cli_db, cli_db):
        import subprocess

        with patch("cortex.cli._get_tmux_panes", return_value={"%50", "%51"}):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout="fish\n", stderr="")
                code, output = _run_cli(["session", "health"])
        assert code == 0
        untracked = [f for f in output["findings"] if f.get("check") == "untracked_pane"]
        assert len(untracked) == 2
