"""
Test: team status queries — active sessions, last_seen freshness, stale flagging.

Spec ref: Cortex CLI Extensions > `cortex team status`
"Shows all team sessions and their status (includes last_seen for staleness)"
Spec ref: Dead Session Detection
"Sessions with null `last_seen` treated as stale immediately"
"`cortex team status` flags sessions with stale heartbeat (>5min) or null last_seen"
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from cortex.cli import cli
from cortex.session_registry import MongoSessionRepo


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ago(minutes: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()


class TestTeamStatus:
    def test_lists_active_team_sessions(self, patch_db, session_repo: MongoSessionRepo):
        session_repo.register(
            "s1",
            {
                "name": "feedback-endpoint",
                "task": "implement feedback endpoint",
                "team": "default",
                "last_seen": _utc_now(),
            },
        )
        session_repo.register(
            "s2",
            {
                "name": "auth-refactor",
                "task": "refactor auth middleware",
                "team": "default",
                "last_seen": _utc_now(),
            },
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["team", "status"])

        assert result.exit_code == 0
        assert "feedback-endpoint" in result.output
        assert "auth-refactor" in result.output

    def test_excludes_non_team_sessions(self, patch_db, session_repo: MongoSessionRepo):
        session_repo.register("s1", {"name": "regular-session"})  # no team field
        session_repo.register(
            "s2",
            {"name": "team-session", "team": "default", "task": "task", "last_seen": _utc_now()},
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["team", "status"])

        assert result.exit_code == 0
        assert "team-session" in result.output
        assert "regular-session" not in result.output

    def test_excludes_completed_and_dead_sessions(
        self, patch_db, session_repo: MongoSessionRepo
    ):
        session_repo.register(
            "s1", {"name": "done-session", "team": "default", "task": "t", "status": "completed"}
        )
        session_repo.register(
            "s2", {"name": "dead-session", "team": "default", "task": "t", "status": "dead"}
        )
        session_repo.register(
            "s3",
            {
                "name": "active-session",
                "team": "default",
                "task": "t",
                "status": "active",
                "last_seen": _utc_now(),
            },
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["team", "status"])

        assert result.exit_code == 0
        assert "active-session" in result.output
        assert "done-session" not in result.output
        assert "dead-session" not in result.output

    def test_flags_stale_session_with_old_last_seen(
        self, patch_db, session_repo: MongoSessionRepo
    ):
        session_repo.register(
            "s-stale",
            {
                "name": "stale-session",
                "team": "default",
                "task": "task",
                "last_seen": _ago(10),  # 10 min > 5-min threshold
            },
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["team", "status"])

        assert result.exit_code == 0
        assert "[stale]" in result.output

    def test_flags_null_last_seen_as_stale(self, patch_db, session_repo: MongoSessionRepo):
        """null last_seen = crashed before first heartbeat — immediately stale."""
        session_repo.register(
            "s-null",
            {
                "name": "never-hearted",
                "team": "default",
                "task": "task",
                "last_seen": None,
            },
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["team", "status"])

        assert result.exit_code == 0
        assert "never-hearted" in result.output
        assert "[stale]" in result.output

    def test_fresh_session_not_flagged(self, patch_db, session_repo: MongoSessionRepo):
        session_repo.register(
            "s-fresh",
            {
                "name": "fresh-session",
                "team": "default",
                "task": "task",
                "last_seen": _ago(1),  # 1 min < 5-min threshold
            },
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["team", "status"])

        assert result.exit_code == 0
        assert "fresh-session" in result.output
        assert "[stale]" not in result.output

    def test_shows_task_column(self, patch_db, session_repo: MongoSessionRepo):
        session_repo.register(
            "s1",
            {
                "name": "feedback-endpoint",
                "task": "implement feedback endpoint (ATS-234)",
                "team": "default",
                "last_seen": _utc_now(),
            },
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["team", "status"])

        assert result.exit_code == 0
        assert "ATS-234" in result.output or "implement feedback" in result.output

    def test_empty_team_returns_no_error(self, patch_db):
        runner = CliRunner()
        result = runner.invoke(cli, ["team", "status"])

        assert result.exit_code == 0

    def test_shows_last_seen_age(self, patch_db, session_repo: MongoSessionRepo):
        session_repo.register(
            "s1",
            {
                "name": "my-session",
                "team": "default",
                "task": "task",
                "last_seen": _ago(2),
            },
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["team", "status"])

        assert result.exit_code == 0
        assert "ago" in result.output


class TestHeartbeatUpdate:
    def test_last_seen_can_be_updated(self, session_repo: MongoSessionRepo):
        """Simulates the TS MCP heartbeat writing last_seen every 30s."""
        session_repo.register(
            "sess-hb",
            {"name": "my-session", "team": "default", "task": "task", "last_seen": None},
        )

        session_repo.update("sess-hb", {"last_seen": _utc_now()})

        updated = session_repo.get("sess-hb")
        assert updated["last_seen"] is not None

    def test_last_seen_updates_overwrite_previous(self, session_repo: MongoSessionRepo):
        session_repo.register(
            "sess-hb2",
            {"name": "hb-session", "team": "default", "task": "task"},
        )

        first_ts = _ago(1)
        session_repo.update("sess-hb2", {"last_seen": first_ts})

        second_ts = _utc_now()
        session_repo.update("sess-hb2", {"last_seen": second_ts})

        updated = session_repo.get("sess-hb2")
        assert updated["last_seen"] == second_ts
