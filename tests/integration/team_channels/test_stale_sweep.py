"""
Test: stale session detection and sweep.

Spec ref: Dead Session Detection > Phase 1
"`cortex team spawn` sweeps stale sessions: marks as dead, expires their pending messages"
"Sessions with null `last_seen` (crashed before first heartbeat) are treated as stale immediately"

Implementation note: _sweep_stale_sessions in cli.py only sweeps sessions with null/missing
last_seen (sessions that never sent a heartbeat = definitely crashed). Sessions with old but
non-null last_seen are flagged in `cortex team status` output but not automatically killed in
Phase 1 (to avoid killing busy-but-slow sessions).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from click.testing import CliRunner
from pymongo.database import Database

from cortex.cli import _sweep_stale_sessions
from cortex.session_registry import MongoSessionRepo


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _minutes_ago(n: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=n)).isoformat()


class TestSweepStaleSessions:
    def test_sweep_marks_null_last_seen_session_dead(self, session_repo: MongoSessionRepo):
        """Sessions with null last_seen = crashed before first heartbeat → dead."""
        session_repo.register(
            "null-hb",
            {
                "name": "no-heartbeat",
                "team": "default",
                "task": "task",
                "status": "active",
                "last_seen": None,
            },
        )

        count = _sweep_stale_sessions(session_repo)

        assert count >= 1
        doc = session_repo.get("null-hb")
        assert doc["status"] == "dead"

    def test_sweep_marks_missing_last_seen_session_dead(self, session_repo: MongoSessionRepo):
        """Sessions without last_seen field at all are treated same as null."""
        session_repo._col.insert_one(
            {
                "_id": "no-field",
                "name": "no-last-seen-field",
                "team": "default",
                "task": "task",
                "status": "active",
                "created_at": _utc_now(),
                "events": [],
                "runtime": "unknown",
            }
        )

        count = _sweep_stale_sessions(session_repo)

        assert count >= 1
        doc = session_repo.get("no-field")
        assert doc["status"] == "dead"

    def test_sweep_expires_pending_messages(
        self, session_repo: MongoSessionRepo, mongo_db: Database
    ):
        """Pending messages for swept sessions are marked delivered (expired)."""
        session_repo.register(
            "stale-msg",
            {
                "name": "stale-target",
                "team": "default",
                "task": "task",
                "status": "active",
                "last_seen": None,
            },
        )
        mongo_db["messages"].insert_many(
            [
                {
                    "_id": f"msg_expire_{i:03d}",
                    "from": "sender",
                    "to": "stale-target",
                    "content": f"msg {i}",
                    "meta": {},
                    "status": "pending",
                    "created_at": _utc_now(),
                    "delivered_at": None,
                }
                for i in range(3)
            ]
        )

        _sweep_stale_sessions(session_repo)

        still_pending = list(
            mongo_db["messages"].find({"to": "stale-target", "status": "pending"})
        )
        assert len(still_pending) == 0

    def test_sweep_does_not_touch_fresh_session_with_heartbeat(
        self, session_repo: MongoSessionRepo
    ):
        """Sessions that have sent at least one heartbeat are not swept."""
        session_repo.register(
            "fresh-1",
            {
                "name": "healthy-session",
                "team": "default",
                "task": "task",
                "status": "active",
                "last_seen": _minutes_ago(1),  # has a heartbeat
            },
        )

        count = _sweep_stale_sessions(session_repo)

        assert count == 0
        doc = session_repo.get("fresh-1")
        assert doc["status"] == "active"

    def test_sweep_does_not_touch_already_dead_sessions(
        self, session_repo: MongoSessionRepo
    ):
        session_repo.register(
            "dead-1",
            {
                "name": "already-dead",
                "team": "default",
                "task": "task",
                "status": "dead",
                "last_seen": None,
            },
        )

        count = _sweep_stale_sessions(session_repo)

        assert count == 0

    def test_sweep_does_not_touch_completed_sessions(
        self, session_repo: MongoSessionRepo
    ):
        session_repo.register(
            "done-1",
            {
                "name": "completed-session",
                "team": "default",
                "task": "task",
                "status": "completed",
                "last_seen": None,
            },
        )

        count = _sweep_stale_sessions(session_repo)

        assert count == 0

    def test_sweep_does_not_touch_non_team_sessions(
        self, session_repo: MongoSessionRepo
    ):
        """Sweep only operates on sessions with the team field."""
        session_repo.register(
            "reg-1",
            {
                "name": "regular-session",
                "task": "task",
                "status": "active",
                "last_seen": None,
                # No "team" field
            },
        )

        count = _sweep_stale_sessions(session_repo)

        assert count == 0
        doc = session_repo.get("reg-1")
        assert doc["status"] == "active"

    def test_sweep_returns_count_of_sessions_swept(self, session_repo: MongoSessionRepo):
        for i in range(3):
            session_repo.register(
                f"stale-{i}",
                {
                    "name": f"stale-session-{i}",
                    "team": "default",
                    "task": "task",
                    "status": "active",
                    "last_seen": None,
                },
            )

        count = _sweep_stale_sessions(session_repo)

        assert count == 3

    def test_sweep_records_trigger_in_events(self, session_repo: MongoSessionRepo):
        session_repo.register(
            "stale-evt",
            {
                "name": "sweep-event-test",
                "team": "default",
                "task": "task",
                "status": "active",
                "last_seen": None,
            },
        )

        _sweep_stale_sessions(session_repo)

        doc = session_repo.get("stale-evt")
        sweep_events = [e for e in doc["events"] if e.get("trigger") == "stale-sweep"]
        assert len(sweep_events) == 1


class TestSpawnTriggersSweep:
    def test_spawn_sweeps_stale_sessions_before_registering(
        self, patch_db, session_repo: MongoSessionRepo
    ):
        """cortex team spawn sweeps stale sessions as a side effect."""
        session_repo.register(
            "pre-stale",
            {
                "name": "pre-existing-stale",
                "team": "default",
                "task": "old task",
                "status": "active",
                "last_seen": None,
            },
        )

        runner = CliRunner()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = type(
                "R", (), {"returncode": 0, "stdout": "%42\n", "stderr": ""}
            )()
            runner.invoke(cli, ["team", "spawn", "--task", "new task"])

        doc = session_repo.get("pre-stale")
        assert doc["status"] == "dead"


try:
    from cortex.cli import cli
except ImportError:
    cli = None  # type: ignore[assignment]
