import json
from unittest.mock import patch

from cortex import server
from cortex.mongo_state import MongoStateManager


class TestSameConnectionVisibility:
    """Entries are immediately visible on the same MongoStateManager that wrote them."""

    def test_update_visible_after_add(self, state: MongoStateManager):
        stream = state.create_stream("Test", ["repo"])
        update = state.add_update(stream.id, "deployed auth module", "Auth deployed")
        results = state.search("auth")
        assert any(r.id == update.id for r in results)

    def test_decision_visible_after_add(self, state: MongoStateManager):
        stream = state.create_stream("Test", ["repo"])
        decision = state.add_decision(stream.id, "Use JWT", "Stateless auth")
        results = state.search("JWT")
        assert any(r.id == decision.id for r in results)

    def test_update_in_stream_context_after_add(self, state: MongoStateManager):
        stream = state.create_stream("Test", ["repo"])
        state.add_update(stream.id, "new feature landed", "Feature landed")
        ctx = state.get_stream_context(stream.id)
        assert len(ctx["updates"]) == 1
        assert ctx["updates"][0]["content"] == "new feature landed"

    def test_decision_in_stream_context_after_add(self, state: MongoStateManager):
        stream = state.create_stream("Test", ["repo"])
        state.add_decision(stream.id, "Use Redis", "Fast cache")
        ctx = state.get_stream_context(stream.id)
        assert len(ctx["decisions"]) == 1
        assert ctx["decisions"][0]["what"] == "Use Redis"

    def test_multiple_writes_all_visible(self, state: MongoStateManager):
        stream = state.create_stream("Test", ["repo"])
        for i in range(5):
            state.add_update(stream.id, f"update {i} about testing", f"Test {i}")
        results = state.search("testing")
        assert len(results) == 5


class TestCrossInstanceVisibility:
    """Entries written by one MongoStateManager are visible to a second (same DB)."""

    def test_update_visible_from_second_instance(self, mongo_db):
        writer = MongoStateManager(mongo_db)
        stream = writer.create_stream("Test", ["repo"])
        writer.add_update(stream.id, "cross-instance content", "Cross-inst update")

        reader = MongoStateManager(mongo_db)
        ctx = reader.get_stream_context(stream.id)
        assert len(ctx["updates"]) == 1
        assert ctx["updates"][0]["content"] == "cross-instance content"

    def test_stream_visible_from_second_instance(self, mongo_db):
        writer = MongoStateManager(mongo_db)
        stream = writer.create_stream("Visible Stream", ["repo"])

        reader = MongoStateManager(mongo_db)
        found = reader.get_stream(stream.id)
        assert found is not None
        assert found.title == "Visible Stream"


class TestMCPWriteThenRead:
    """MCP tool writes are immediately queryable via MCP tool reads."""

    def test_log_update_then_search(self, state: MongoStateManager):
        stream = state.create_stream("MCP Test", ["repo"])
        with patch.object(server, "_state", state):
            raw = server.cortex_log_update(stream.id, "deployed new service", "Service deployed")
            data = json.loads(raw)
            assert "id" in data

            search_raw = server.cortex_search_history("deployed")
            search_data = json.loads(search_raw)
            assert len(search_data["results"]) >= 1
            assert any("deployed" in r.get("content", "") for r in search_data["results"])

    def test_log_decision_then_search(self, state: MongoStateManager):
        stream = state.create_stream("MCP Test", ["repo"])
        with patch.object(server, "_state", state):
            raw = server.cortex_log_decision(stream.id, "Use PostgreSQL", "ACID compliance needed")
            data = json.loads(raw)
            assert "id" in data

            search_raw = server.cortex_search_history("PostgreSQL")
            search_data = json.loads(search_raw)
            assert len(search_data["results"]) >= 1

    def test_log_update_then_get_context(self, state: MongoStateManager):
        stream = state.create_stream("MCP Test", ["repo"])
        with patch.object(server, "_state", state):
            server.cortex_log_update(stream.id, "context visible content", "Context test")
            ctx_raw = server.cortex_get_context("context visible")
            ctx_data = json.loads(ctx_raw)
            assert len(ctx_data["results"]) >= 1
