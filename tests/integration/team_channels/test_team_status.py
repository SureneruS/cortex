"""Test: heartbeat updates — last_seen field tracking."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from cortex.session_registry import MongoSessionRepo


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ago(minutes: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()


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
