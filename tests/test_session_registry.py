from __future__ import annotations

import json
import os
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


def test_resolve_by_exact_id(session_repo):
    session_repo.register("sess-abc", {"name": "my-session"})
    doc = session_repo.resolve("sess-abc")
    assert doc is not None
    assert doc["_id"] == "sess-abc"


def test_resolve_by_name(session_repo):
    session_repo.register("s1", {"name": "unique-name"})
    doc = session_repo.resolve("unique-name")
    assert doc is not None
    assert doc["_id"] == "s1"


def test_resolve_by_name_ignores_completed(session_repo):
    session_repo.register("s1", {"name": "worker"})
    session_repo.register("s2", {"name": "worker", "status": "completed"})
    doc = session_repo.resolve("worker")
    assert doc["_id"] == "s1"


def test_resolve_ambiguous_name_raises(session_repo):
    session_repo.register("s1", {"name": "worker"})
    session_repo.register("s2", {"name": "worker"})
    with pytest.raises(ValueError, match="Ambiguous name"):
        session_repo.resolve("worker")


def test_resolve_by_id_prefix(session_repo):
    session_repo.register("abcdef123456", {"name": "test"})
    doc = session_repo.resolve("abcdef")
    assert doc is not None
    assert doc["_id"] == "abcdef123456"


def test_resolve_not_found(session_repo):
    assert session_repo.resolve("nonexistent") is None


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


# --- cc_sessions tracking (CTX-63/CTX-68) ---


def test_register_with_cc_session_id_initializes_array(session_repo):
    doc = session_repo.register("s1", {"name": "test", "cc_session_id": "cc-aaa"})
    assert doc["cc_session_id"] == "cc-aaa"
    assert len(doc["cc_sessions"]) == 1
    assert doc["cc_sessions"][0]["cc_session_id"] == "cc-aaa"
    assert "started_at" in doc["cc_sessions"][0]


def test_register_without_cc_session_id_no_array(session_repo):
    doc = session_repo.register("s1", {"name": "test"})
    assert doc.get("cc_session_id") is None
    assert "cc_sessions" not in doc


def test_append_cc_session_adds_to_array(session_repo):
    session_repo.register("s1", {"name": "test", "cc_session_id": "cc-aaa"})
    updated = session_repo.append_cc_session("s1", "cc-bbb")
    assert updated["cc_session_id"] == "cc-bbb"
    assert len(updated["cc_sessions"]) == 2
    assert updated["cc_sessions"][0]["cc_session_id"] == "cc-aaa"
    assert updated["cc_sessions"][1]["cc_session_id"] == "cc-bbb"


def test_append_cc_session_with_extra(session_repo):
    session_repo.register("s1", {"name": "test", "cc_session_id": "cc-aaa"})
    updated = session_repo.append_cc_session(
        "s1", "cc-bbb", extra={"transcript_path": "/tmp/t.jsonl", "cc_version": "1.2.3"}
    )
    entry = updated["cc_sessions"][1]
    assert entry["cc_session_id"] == "cc-bbb"
    assert entry["transcript_path"] == "/tmp/t.jsonl"
    assert entry["cc_version"] == "1.2.3"


def test_append_cc_session_nonexistent(session_repo):
    assert session_repo.append_cc_session("nope", "cc-aaa") is None


def test_append_cc_session_on_session_without_initial_array(session_repo):
    """Sessions registered without cc_session_id get array created on first link."""
    session_repo.register("s1", {"name": "test"})
    updated = session_repo.append_cc_session("s1", "cc-aaa")
    assert updated["cc_session_id"] == "cc-aaa"
    assert len(updated["cc_sessions"]) == 1
    assert updated["cc_sessions"][0]["cc_session_id"] == "cc-aaa"


# --- Dedup: race condition at spawn time (CTX-94) ---


def test_register_dedup_same_cc_session_id(session_repo):
    """Two rapid register calls with the same cc_session_id produce only one document."""
    data = {"name": "manual", "cc_session_id": "cc-dup", "spawned_by": "manual"}
    doc1 = session_repo.register(None, data.copy())
    doc2 = session_repo.register(None, data.copy())
    assert doc1["_id"] == doc2["_id"]
    all_docs = session_repo.list({"cc_session_id": "cc-dup"})
    assert len(all_docs) == 1


def test_register_dedup_allows_different_cc_session_ids(session_repo):
    """Different cc_session_ids still create separate documents."""
    doc1 = session_repo.register(None, {"name": "s1", "cc_session_id": "cc-aaa"})
    doc2 = session_repo.register(None, {"name": "s2", "cc_session_id": "cc-bbb"})
    assert doc1["_id"] != doc2["_id"]


def test_register_dedup_allows_reuse_after_completed(session_repo):
    """A completed session's cc_session_id can be reused for a new registration."""
    doc1 = session_repo.register("s1", {"name": "test", "cc_session_id": "cc-reuse"})
    session_repo.close("s1")
    doc2 = session_repo.register(None, {"name": "test2", "cc_session_id": "cc-reuse"})
    assert doc2["_id"] != doc1["_id"]


def test_append_cc_session_dedup_same_cc_session_id(session_repo):
    """Two rapid link-cc calls with the same cc_session_id don't duplicate the array entry."""
    session_repo.register("s1", {"name": "test", "cc_session_id": "cc-aaa"})
    session_repo.append_cc_session("s1", "cc-bbb")
    session_repo.append_cc_session("s1", "cc-bbb")
    doc = session_repo.get("s1")
    assert doc["cc_session_id"] == "cc-bbb"
    cc_ids = [e["cc_session_id"] for e in doc["cc_sessions"]]
    assert cc_ids == ["cc-aaa", "cc-bbb"]


def test_resolve_by_old_cc_session_id(session_repo):
    """After /clear, resolve should still find session by its previous cc_session_id."""
    session_repo.register("s1", {"name": "test", "cc_session_id": "cc-aaa"})
    session_repo.append_cc_session("s1", "cc-bbb")
    # cc_session_id is now cc-bbb, but cc-aaa is in cc_sessions array
    doc = session_repo.resolve("cc-aaa")
    assert doc is not None
    assert doc["_id"] == "s1"


def test_resolve_by_current_cc_session_id(session_repo):
    session_repo.register("s1", {"name": "test", "cc_session_id": "cc-aaa"})
    session_repo.append_cc_session("s1", "cc-bbb")
    doc = session_repo.resolve("cc-bbb")
    assert doc is not None
    assert doc["_id"] == "s1"


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
    from cortex.container import reset_container
    reset_container()
    with patch("cortex.mongo.get_db", return_value=cli_db):
        yield
    reset_container()


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
def _seed_session_with_pane(cli_db):
    repo = MongoSessionRepo(cli_db)
    repo.register("cli-pane-1", {"name": "pane-session", "pane_id": "%42"})


def _no_session_env():
    """Remove CORTEX_SESSION_ID so close permission check sees 'human' (always allowed)."""
    env = {k: v for k, v in os.environ.items() if k != "CORTEX_SESSION_ID"}
    return patch.dict(os.environ, env, clear=True)


class TestCLIClose:
    def test_close_session_no_pane(self, _patch_cli_db, _seed_session):
        with _no_session_env(), patch("cortex.adapters.tmux.TmuxAdapter.pane_exists", return_value=False):
            code, output = _run_cli(["session", "close", "cli-test-1"])
        assert code == 0
        assert output["status"] == "completed"
        assert "closed_at" in output

    def test_close_nonexistent_session(self, _patch_cli_db):
        code, output = _run_cli(["session", "close", "nope"])
        assert code == 1
        assert "not found" in output["error"]

    def test_close_force_skips_wrapup(self, _patch_cli_db, _seed_session_with_pane):
        with (
            _no_session_env(),
            patch("cortex.adapters.tmux.TmuxAdapter.pane_exists", return_value=True),
            patch("cortex.adapters.tmux.TmuxAdapter.send_text") as send,
            patch("cortex.adapters.tmux.TmuxAdapter.destroy_pane", return_value=True) as kill,
        ):
            code, output = _run_cli(["session", "close", "cli-pane-1", "--force"])
        assert code == 0
        assert output["status"] == "completed"
        send.assert_not_called()
        kill.assert_called_once_with("%42")

    def test_close_lifecycle_with_pane(self, _patch_cli_db, _seed_session_with_pane):
        with (
            _no_session_env(),
            patch("cortex.adapters.tmux.TmuxAdapter.pane_exists", return_value=True),
            patch("cortex.adapters.tmux.TmuxAdapter.send_text", return_value=True) as send,
            patch("cortex.adapters.tmux.TmuxAdapter.wait_for_idle", return_value=True) as wait,
            patch("cortex.adapters.tmux.TmuxAdapter.destroy_pane", return_value=True) as kill,
            patch("time.sleep"),
        ):
            code, output = _run_cli(["session", "close", "cli-pane-1"])
        assert code == 0
        assert output["status"] == "completed"
        send.assert_any_call("%42", "/session-wrapup")
        kill.assert_called_once_with("%42")

    def test_close_pane_gone_skips_terminal(
        self, _patch_cli_db, _seed_session_with_pane
    ):
        with (
            _no_session_env(),
            patch("cortex.adapters.tmux.TmuxAdapter.pane_exists", return_value=False),
            patch("cortex.adapters.tmux.TmuxAdapter.send_text") as send,
            patch("cortex.adapters.tmux.TmuxAdapter.destroy_pane") as kill,
        ):
            code, output = _run_cli(["session", "close", "cli-pane-1"])
        assert code == 0
        assert output["status"] == "completed"
        send.assert_not_called()
        kill.assert_not_called()

    def test_close_wrapup_timeout_continues(
        self, _patch_cli_db, _seed_session_with_pane
    ):
        with (
            _no_session_env(),
            patch("cortex.adapters.tmux.TmuxAdapter.pane_exists", return_value=True),
            patch("cortex.adapters.tmux.TmuxAdapter.send_text", return_value=True),
            patch("cortex.adapters.tmux.TmuxAdapter.wait_for_idle", return_value=False),
            patch("cortex.adapters.tmux.TmuxAdapter.destroy_pane", return_value=True) as kill,
            patch("time.sleep"),
        ):
            code, output = _run_cli(["session", "close", "cli-pane-1"])
        assert code == 0
        assert output["status"] == "completed"
        kill.assert_called_once_with("%42")


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
            patch("cortex.adapters.tmux.TmuxAdapter.list_pane_ids", return_value={"%42"}),
            patch("cortex.adapters.tmux.TmuxAdapter.capture_output", return_value="Working on task..."),
            patch("cortex.adapters.tmux.TmuxAdapter.display_message", return_value=""),
        ):
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
        with patch("cortex.adapters.tmux.TmuxAdapter.list_pane_ids", return_value=set()):
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
            patch("cortex.adapters.tmux.TmuxAdapter.list_pane_ids", return_value={"%99"}),
            patch("cortex.adapters.tmux.TmuxAdapter.capture_output", return_value="❯ "),
            patch("cortex.adapters.tmux.TmuxAdapter.display_message", return_value=""),
        ):
            code, output = _run_cli(["session", "health"])
        assert code == 0
        stale = [f for f in output["findings"] if f.get("check") == "stale"]
        assert len(stale) == 1
        assert stale[0]["hours_since_activity"] > 24

    def test_health_detects_untracked_panes(self, _patch_cli_db, cli_db):
        with (
            patch("cortex.adapters.tmux.TmuxAdapter.list_pane_ids", return_value={"%50", "%51"}),
            patch("cortex.adapters.tmux.TmuxAdapter.display_message", return_value="fish"),
        ):
            code, output = _run_cli(["session", "health"])
        assert code == 0
        untracked = [f for f in output["findings"] if f.get("check") == "untracked_pane"]
        assert len(untracked) == 2


class TestCLILinkCC:
    def test_link_cc_appends_to_array(self, _patch_cli_db, cli_db):
        repo = MongoSessionRepo(cli_db)
        repo.register("s1", {"name": "test", "cc_session_id": "cc-aaa"})
        code, output = _run_cli(["session", "link-cc", "s1", "cc-bbb"])
        assert code == 0
        assert output["cc_session_id"] == "cc-bbb"
        assert len(output["cc_sessions"]) == 2

    def test_link_cc_with_extra_data(self, _patch_cli_db, cli_db):
        repo = MongoSessionRepo(cli_db)
        repo.register("s1", {"name": "test", "cc_session_id": "cc-aaa"})
        code, output = _run_cli([
            "session", "link-cc", "s1", "cc-bbb",
            "--data", '{"transcript_path": "/tmp/t.jsonl"}',
        ])
        assert code == 0
        assert output["cc_sessions"][1]["transcript_path"] == "/tmp/t.jsonl"

    def test_link_cc_nonexistent_session(self, _patch_cli_db):
        code, output = _run_cli(["session", "link-cc", "nope", "cc-aaa"])
        assert code == 1
        assert "not found" in output["error"]


class TestSessionStartHookClearLifecycle:
    """CTX-68: /clear fires SessionStart again — should update, not duplicate."""

    def test_clear_calls_link_cc_not_register(self):
        """On /clear with active session: calls link-cc and update, never register."""
        from nova.hooks.session_start import handle_session_start

        existing = json.dumps({"status": "active", "name": "worker", "repos": ["cortex"]})
        calls = []

        def fake_cortex_cli(*args):
            calls.append(args)
            if args[:2] == ("session", "get"):
                return existing
            return "{}"

        with (
            patch("nova.hooks.session_start._cortex_cli", side_effect=fake_cortex_cli),
            patch.dict(os.environ, {"CORTEX_SESSION_ID": "ctx-1"}),
        ):
            handle_session_start({
                "session_id": "cc-second",
                "transcript_path": "/tmp/t2.jsonl",
                "cwd": "/Users/test/workspace/cercli/cortex",
            })

        cmds = [c[:2] for c in calls]
        assert ("session", "get") in cmds
        assert ("session", "link-cc") in cmds
        assert ("session", "update") in cmds
        assert ("session", "register") not in cmds

        link_call = next(c for c in calls if c[:2] == ("session", "link-cc"))
        assert link_call[2] == "ctx-1"
        assert link_call[3] == "cc-second"

    def test_clear_on_dead_session_reactivates_then_links(self):
        """If session was dead, hook reactivates it before linking new CC session."""
        from nova.hooks.session_start import handle_session_start

        existing = json.dumps({"status": "dead", "name": "worker", "repos": ["cortex"]})
        calls = []

        def fake_cortex_cli(*args):
            calls.append(args)
            if args[:2] == ("session", "get"):
                return existing
            return "{}"

        with (
            patch("nova.hooks.session_start._cortex_cli", side_effect=fake_cortex_cli),
            patch.dict(os.environ, {"CORTEX_SESSION_ID": "ctx-1"}),
        ):
            handle_session_start({
                "session_id": "cc-second",
                "transcript_path": "/tmp/t2.jsonl",
                "cwd": "/Users/test/workspace/cercli/cortex",
            })

        cmds = [c[:2] for c in calls]
        assert ("session", "register") not in cmds

        # Should have: get, update (reactivate), link-cc, update (fields)
        update_calls = [c for c in calls if c[:2] == ("session", "update")]
        assert len(update_calls) == 2

        # First update reactivates
        reactivate = update_calls[0]
        reactivate_data = json.loads(reactivate[4])  # --data value
        assert reactivate_data["status"] == "active"
        assert reactivate[6] == "clear_reactivate"  # --trigger value

        # link-cc was called
        assert ("session", "link-cc") in cmds

    def test_no_cortex_session_id_registers_new(self):
        """Without CORTEX_SESSION_ID env var, hook registers a new session."""
        from nova.hooks.session_start import handle_session_start

        calls = []

        def fake_cortex_cli(*args):
            calls.append(args)
            return "{}"

        with (
            patch("nova.hooks.session_start._cortex_cli", side_effect=fake_cortex_cli),
            patch.dict(os.environ, {}, clear=False),
        ):
            os.environ.pop("CORTEX_SESSION_ID", None)
            handle_session_start({
                "session_id": "cc-new",
                "transcript_path": "/tmp/t.jsonl",
                "cwd": "/Users/test/workspace/cercli/cortex",
            })

        cmds = [c[:2] for c in calls]
        assert ("session", "register") in cmds
        assert ("session", "link-cc") not in cmds

    def test_cortex_session_not_found_registers_with_id(self):
        """If CORTEX_SESSION_ID is set but session doesn't exist, register with that ID."""
        from nova.hooks.session_start import handle_session_start

        calls = []

        def fake_cortex_cli(*args):
            calls.append(args)
            if args[:2] == ("session", "get"):
                return None
            return "{}"

        with (
            patch("nova.hooks.session_start._cortex_cli", side_effect=fake_cortex_cli),
            patch.dict(os.environ, {"CORTEX_SESSION_ID": "ctx-orphan"}),
        ):
            handle_session_start({
                "session_id": "cc-new",
                "transcript_path": "/tmp/t.jsonl",
                "cwd": "/Users/test/workspace/cercli/cortex",
            })

        cmds = [c[:2] for c in calls]
        assert ("session", "register") in cmds
        register_call = next(c for c in calls if c[:2] == ("session", "register"))
        assert "--id" in register_call
        id_idx = list(register_call).index("--id")
        assert register_call[id_idx + 1] == "ctx-orphan"


# --- Sub-session spawning (parent_id, limits, close permissions) ---


class TestParentId:
    def test_register_with_parent_id(self, session_repo):
        session_repo.register("parent-1", {"name": "control", "role": "control"})
        session_repo.register("child-1", {"name": "worker-a", "parent_id": "parent-1"})
        child = session_repo.get("child-1")
        assert child["parent_id"] == "parent-1"

    def test_register_without_parent_id(self, session_repo):
        doc = session_repo.register("s1", {"name": "standalone"})
        assert doc.get("parent_id") is None

    def test_list_children_by_parent_id(self, session_repo):
        session_repo.register("parent-1", {"name": "control"})
        session_repo.register("child-1", {"name": "w-a", "parent_id": "parent-1"})
        session_repo.register("child-2", {"name": "w-b", "parent_id": "parent-1"})
        session_repo.register("other", {"name": "w-c", "parent_id": "other-parent"})
        children = session_repo.list({"parent_id": "parent-1"})
        assert len(children) == 2
        assert {c["name"] for c in children} == {"w-a", "w-b"}


class TestSpawnLimit:
    def test_spawn_denied_at_limit(self, _patch_cli_db, cli_db):
        from datetime import datetime, timezone
        from cortex.services.session_service import MAX_ACTIVE_SESSIONS
        repo = MongoSessionRepo(cli_db)
        now = datetime.now(timezone.utc).isoformat()
        for i in range(MAX_ACTIVE_SESSIONS):
            repo.register(f"s{i}", {"name": f"session-{i}", "last_seen": now})
        with patch("cortex.adapters.tmux.TmuxAdapter.pane_exists", return_value=False):
            code, output = _run_cli([
                "session", "spawn", "--name", "overflow",
            ])
        assert code == 1
        assert "session limit" in output["error"].lower()

    def test_spawn_ok_below_limit(self, _patch_cli_db, cli_db):
        from datetime import datetime, timezone
        repo = MongoSessionRepo(cli_db)
        repo.register("s1", {"name": "existing", "last_seen": datetime.now(timezone.utc).isoformat()})
        with (
            patch("cortex.adapters.tmux.TmuxAdapter.create_pane", return_value="%99"),
            patch("cortex.adapters.tmux.TmuxAdapter.send_keys"),
            patch("cortex.adapters.tmux.TmuxAdapter.spawn_background_sender"),
            patch("cortex.adapters.tmux.TmuxAdapter.pane_exists", return_value=True),
            patch("time.sleep"),
        ):
            code, output = _run_cli(["session", "spawn", "--name", "new-worker"])
        assert code == 0
        assert output["name"] == "new-worker"

    def test_spawn_ok_when_dead_sessions_dont_count(self, _patch_cli_db, cli_db):
        from cortex.services.session_service import MAX_ACTIVE_SESSIONS
        repo = MongoSessionRepo(cli_db)
        for i in range(MAX_ACTIVE_SESSIONS):
            repo.register(f"s{i}", {"name": f"session-{i}", "status": "completed"})
        with (
            patch("cortex.adapters.tmux.TmuxAdapter.create_pane", return_value="%99"),
            patch("cortex.adapters.tmux.TmuxAdapter.send_keys"),
            patch("cortex.adapters.tmux.TmuxAdapter.spawn_background_sender"),
            patch("cortex.adapters.tmux.TmuxAdapter.pane_exists", return_value=True),
            patch("time.sleep"),
        ):
            code, output = _run_cli(["session", "spawn", "--name", "fresh"])
        assert code == 0


class TestClosePermission:
    def test_human_can_close_any(self, _patch_cli_db, _seed_session):
        """No CORTEX_SESSION_ID means human — can close any session."""
        with (
            _no_session_env(),
            patch("cortex.adapters.tmux.TmuxAdapter.pane_exists", return_value=False),
        ):
            code, output = _run_cli(["session", "close", "cli-test-1"])
        assert code == 0
        assert output["status"] == "completed"

    def test_self_close_allowed(self, _patch_cli_db, cli_db):
        repo = MongoSessionRepo(cli_db)
        repo.register("self-1", {"name": "self-closer"})
        with (
            patch.dict(os.environ, {"CORTEX_SESSION_ID": "self-1"}),
            patch("cortex.adapters.tmux.TmuxAdapter.pane_exists", return_value=False),
        ):
            code, output = _run_cli(["session", "close", "self-1"])
        assert code == 0

    def test_parent_can_close_child(self, _patch_cli_db, cli_db):
        repo = MongoSessionRepo(cli_db)
        repo.register("parent-1", {"name": "parent"})
        repo.register("child-1", {"name": "child", "parent_id": "parent-1"})
        with (
            patch.dict(os.environ, {"CORTEX_SESSION_ID": "parent-1"}),
            patch("cortex.adapters.tmux.TmuxAdapter.pane_exists", return_value=False),
        ):
            code, output = _run_cli(["session", "close", "child-1"])
        assert code == 0
        assert output["status"] == "completed"

    def test_grandparent_can_close_grandchild(self, _patch_cli_db, cli_db):
        repo = MongoSessionRepo(cli_db)
        repo.register("gp", {"name": "grandparent"})
        repo.register("p", {"name": "parent", "parent_id": "gp"})
        repo.register("c", {"name": "child", "parent_id": "p"})
        with (
            patch.dict(os.environ, {"CORTEX_SESSION_ID": "gp"}),
            patch("cortex.adapters.tmux.TmuxAdapter.pane_exists", return_value=False),
        ):
            code, output = _run_cli(["session", "close", "c"])
        assert code == 0

    def test_sibling_cannot_close(self, _patch_cli_db, cli_db):
        repo = MongoSessionRepo(cli_db)
        repo.register("parent-1", {"name": "parent"})
        repo.register("sib-a", {"name": "sibling-a", "parent_id": "parent-1"})
        repo.register("sib-b", {"name": "sibling-b", "parent_id": "parent-1"})
        with (
            patch.dict(os.environ, {"CORTEX_SESSION_ID": "sib-a"}),
            patch("cortex.adapters.tmux.TmuxAdapter.pane_exists", return_value=False),
        ):
            code, output = _run_cli(["session", "close", "sib-b"])
        assert code == 1
        assert "not an ancestor" in output["error"].lower()

    def test_child_cannot_close_parent(self, _patch_cli_db, cli_db):
        repo = MongoSessionRepo(cli_db)
        repo.register("parent-1", {"name": "parent"})
        repo.register("child-1", {"name": "child", "parent_id": "parent-1"})
        with (
            patch.dict(os.environ, {"CORTEX_SESSION_ID": "child-1"}),
            patch("cortex.adapters.tmux.TmuxAdapter.pane_exists", return_value=False),
        ):
            code, output = _run_cli(["session", "close", "parent-1"])
        assert code == 1
        assert "not an ancestor" in output["error"].lower()


class TestCascadeClose:
    def test_cascade_closes_children(self, _patch_cli_db, cli_db):
        repo = MongoSessionRepo(cli_db)
        repo.register("parent-1", {"name": "parent"})
        repo.register("child-1", {"name": "child-a", "parent_id": "parent-1"})
        repo.register("child-2", {"name": "child-b", "parent_id": "parent-1"})
        with (
            _no_session_env(),
            patch("cortex.adapters.tmux.TmuxAdapter.pane_exists", return_value=False),
        ):
            code, output = _run_cli(["session", "close", "parent-1", "--cascade"])
        assert code == 0
        assert output["status"] == "completed"
        assert repo.get("child-1")["status"] == "completed"
        assert repo.get("child-2")["status"] == "completed"

    def test_cascade_closes_grandchildren(self, _patch_cli_db, cli_db):
        repo = MongoSessionRepo(cli_db)
        repo.register("gp", {"name": "grandparent"})
        repo.register("p", {"name": "parent", "parent_id": "gp"})
        repo.register("c", {"name": "child", "parent_id": "p"})
        with (
            _no_session_env(),
            patch("cortex.adapters.tmux.TmuxAdapter.pane_exists", return_value=False),
        ):
            code, output = _run_cli(["session", "close", "gp", "--cascade"])
        assert code == 0
        assert repo.get("p")["status"] == "completed"
        assert repo.get("c")["status"] == "completed"

    def test_cascade_skips_already_dead(self, _patch_cli_db, cli_db):
        repo = MongoSessionRepo(cli_db)
        repo.register("parent-1", {"name": "parent"})
        repo.register("dead-child", {"name": "dead", "parent_id": "parent-1", "status": "completed"})
        repo.register("live-child", {"name": "live", "parent_id": "parent-1"})
        with (
            _no_session_env(),
            patch("cortex.adapters.tmux.TmuxAdapter.pane_exists", return_value=False),
        ):
            code, output = _run_cli(["session", "close", "parent-1", "--cascade"])
        assert code == 0
        assert repo.get("live-child")["status"] == "completed"


class TestChildrenCommand:
    def test_children_lists_active_only(self, _patch_cli_db, cli_db):
        repo = MongoSessionRepo(cli_db)
        repo.register("parent-1", {"name": "parent"})
        repo.register("c1", {"name": "active-child", "parent_id": "parent-1"})
        repo.register("c2", {"name": "dead-child", "parent_id": "parent-1", "status": "completed"})
        code, output = _run_cli(["session", "children", "parent-1"])
        assert code == 0
        assert len(output) == 1
        assert output[0]["name"] == "active-child"

    def test_children_all_flag(self, _patch_cli_db, cli_db):
        repo = MongoSessionRepo(cli_db)
        repo.register("parent-1", {"name": "parent"})
        repo.register("c1", {"name": "active-child", "parent_id": "parent-1"})
        repo.register("c2", {"name": "dead-child", "parent_id": "parent-1", "status": "completed"})
        code, output = _run_cli(["session", "children", "parent-1", "--all"])
        assert code == 0
        assert len(output) == 2


class TestTreeCommand:
    def test_tree_shows_hierarchy(self, _patch_cli_db, cli_db):
        repo = MongoSessionRepo(cli_db)
        repo.register("root", {"name": "control", "role": "control"})
        repo.register("w1", {"name": "worker-1", "parent_id": "root"})
        repo.register("w2", {"name": "worker-2", "parent_id": "root"})
        repo.register("sw1", {"name": "sub-worker", "parent_id": "w1"})
        code, output = _run_cli(["session", "tree", "root"])
        assert code == 0
        assert len(output) == 1
        root_node = output[0]
        assert root_node["name"] == "control"
        assert len(root_node["children"]) == 2
        w1_node = next(c for c in root_node["children"] if c["name"] == "worker-1")
        assert len(w1_node["children"]) == 1
        assert w1_node["children"][0]["name"] == "sub-worker"

    def test_tree_all_roots(self, _patch_cli_db, cli_db):
        repo = MongoSessionRepo(cli_db)
        repo.register("r1", {"name": "root-1"})
        repo.register("r2", {"name": "root-2"})
        repo.register("c1", {"name": "child", "parent_id": "r1"})
        code, output = _run_cli(["session", "tree"])
        assert code == 0
        assert len(output) == 2
