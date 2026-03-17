import json
from pathlib import Path
from unittest.mock import patch

from cortex import server
from cortex.state import StateManager


def _setup_state(tmp_path: Path) -> StateManager:
    sm = StateManager(tmp_path / "test.db")
    sm.init_db()
    stream = sm.create_stream("Test stream", ["test-repo"])
    sm.add_update(stream.id, "Deployed new auth module with OAuth2 flow", "Auth module deployed")
    sm.add_decision(stream.id, "Use JWT for session tokens", "Stateless auth, easy horizontal scaling")
    return sm


class TestSearchHistoryResponse:
    def test_includes_content_field_in_updates(self, tmp_path: Path):
        state = _setup_state(tmp_path)
        with patch.object(server, "_state", state):
            raw = server.cortex_search_history("auth")
        data = json.loads(raw)
        updates = [r for r in data["results"] if r["type"] == "update"]
        assert len(updates) >= 1
        assert "content" in updates[0]
        assert "auth" in updates[0]["content"].lower()

    def test_response_wraps_in_object_with_query(self, tmp_path: Path):
        state = _setup_state(tmp_path)
        with patch.object(server, "_state", state):
            raw = server.cortex_search_history("auth")
        data = json.loads(raw)
        assert "query" in data
        assert data["query"] == "auth"
        assert "results" in data

    def test_consistent_with_get_context(self, tmp_path: Path):
        state = _setup_state(tmp_path)
        with patch.object(server, "_state", state):
            search_raw = server.cortex_search_history("auth")
            context_raw = server.cortex_get_context("auth")
        search_data = json.loads(search_raw)
        context_data = json.loads(context_raw)
        assert len(search_data["results"]) == len(context_data["results"])
