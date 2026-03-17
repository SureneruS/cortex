import json
import sqlite3
from pathlib import Path
from unittest.mock import patch

from cortex import server
from cortex.state import StateManager


class TestSameConnectionVisibility:
    """Entries are immediately visible on the same StateManager that wrote them."""

    def test_update_visible_after_add(self, state: StateManager):
        stream = state.create_stream("Test", ["repo"])
        update = state.add_update(stream.id, "deployed auth module", "Auth deployed")
        results = state.search("auth")
        assert any(r.id == update.id for r in results)

    def test_decision_visible_after_add(self, state: StateManager):
        stream = state.create_stream("Test", ["repo"])
        decision = state.add_decision(stream.id, "Use JWT", "Stateless auth")
        results = state.search("JWT")
        assert any(r.id == decision.id for r in results)

    def test_update_in_stream_context_after_add(self, state: StateManager):
        stream = state.create_stream("Test", ["repo"])
        state.add_update(stream.id, "new feature landed", "Feature landed")
        ctx = state.get_stream_context(stream.id)
        assert len(ctx["updates"]) == 1
        assert ctx["updates"][0]["content"] == "new feature landed"

    def test_decision_in_stream_context_after_add(self, state: StateManager):
        stream = state.create_stream("Test", ["repo"])
        state.add_decision(stream.id, "Use Redis", "Fast cache")
        ctx = state.get_stream_context(stream.id)
        assert len(ctx["decisions"]) == 1
        assert ctx["decisions"][0]["what"] == "Use Redis"

    def test_multiple_writes_all_visible(self, state: StateManager):
        stream = state.create_stream("Test", ["repo"])
        for i in range(5):
            state.add_update(stream.id, f"update {i} about testing", f"Test {i}")
        results = state.search("testing")
        assert len(results) == 5


class TestCrossConnectionVisibility:
    """Entries written by one connection are visible to a second connection (WAL readers)."""

    def test_update_visible_from_second_connection(self, tmp_path: Path):
        db_path = tmp_path / "test.db"
        writer = StateManager(db_path)
        writer.init_db()
        stream = writer.create_stream("Test", ["repo"])
        writer.add_update(stream.id, "cross-connection content", "Cross-conn update")

        reader = StateManager(db_path)
        reader.init_db()
        results = reader.search("cross-connection")
        assert len(results) == 1
        assert results[0].content == "cross-connection content"
        reader.close()
        writer.close()

    def test_decision_visible_from_second_connection(self, tmp_path: Path):
        db_path = tmp_path / "test.db"
        writer = StateManager(db_path)
        writer.init_db()
        stream = writer.create_stream("Test", ["repo"])
        writer.add_decision(stream.id, "Cross-conn decision", "Testing visibility")

        reader = StateManager(db_path)
        reader.init_db()
        results = reader.search("Cross-conn")
        assert len(results) == 1
        assert results[0].what == "Cross-conn decision"
        reader.close()
        writer.close()

    def test_stream_visible_from_second_connection(self, tmp_path: Path):
        db_path = tmp_path / "test.db"
        writer = StateManager(db_path)
        writer.init_db()
        stream = writer.create_stream("Visible Stream", ["repo"])

        reader = StateManager(db_path)
        reader.init_db()
        found = reader.get_stream(stream.id)
        assert found is not None
        assert found.title == "Visible Stream"
        reader.close()
        writer.close()

    def test_context_visible_from_second_connection(self, tmp_path: Path):
        db_path = tmp_path / "test.db"
        writer = StateManager(db_path)
        writer.init_db()
        stream = writer.create_stream("Context Test", ["repo"])
        writer.add_update(stream.id, "visible content", "Visible update")
        writer.add_decision(stream.id, "visible decision", "visible reason")

        reader = StateManager(db_path)
        reader.init_db()
        ctx = reader.get_stream_context(stream.id)
        assert len(ctx["updates"]) == 1
        assert len(ctx["decisions"]) == 1
        reader.close()
        writer.close()


class TestMCPWriteThenRead:
    """MCP tool writes are immediately queryable via MCP tool reads."""

    def test_log_update_then_search(self, tmp_path: Path):
        state = StateManager(tmp_path / "test.db")
        state.init_db()
        stream = state.create_stream("MCP Test", ["repo"])
        with patch.object(server, "_state", state):
            raw = server.cortex_log_update(stream.id, "deployed new service", "Service deployed")
            data = json.loads(raw)
            assert "id" in data

            search_raw = server.cortex_search_history("deployed")
            search_data = json.loads(search_raw)
            assert len(search_data["results"]) >= 1
            assert any("deployed" in r.get("content", "") for r in search_data["results"])

    def test_log_decision_then_search(self, tmp_path: Path):
        state = StateManager(tmp_path / "test.db")
        state.init_db()
        stream = state.create_stream("MCP Test", ["repo"])
        with patch.object(server, "_state", state):
            raw = server.cortex_log_decision(stream.id, "Use PostgreSQL", "ACID compliance needed")
            data = json.loads(raw)
            assert "id" in data

            search_raw = server.cortex_search_history("PostgreSQL")
            search_data = json.loads(search_raw)
            assert len(search_data["results"]) >= 1

    def test_log_update_then_get_context(self, tmp_path: Path):
        state = StateManager(tmp_path / "test.db")
        state.init_db()
        stream = state.create_stream("MCP Test", ["repo"])
        with patch.object(server, "_state", state):
            server.cortex_log_update(stream.id, "context visible content", "Context test")
            ctx_raw = server.cortex_get_context("context visible")
            ctx_data = json.loads(ctx_raw)
            assert len(ctx_data["results"]) >= 1


class TestRawSQLiteVisibility:
    """Entries are visible via raw sqlite3 queries (simulating external tools)."""

    def test_update_visible_via_raw_sqlite(self, tmp_path: Path):
        db_path = tmp_path / "test.db"
        state = StateManager(db_path)
        state.init_db()
        stream = state.create_stream("Raw SQL Test", ["repo"])
        state.add_update(stream.id, "raw sql visible content", "Raw SQL test")

        raw_conn = sqlite3.connect(str(db_path))
        row = raw_conn.execute(
            "SELECT content FROM updates WHERE content LIKE '%raw sql visible%'"
        ).fetchone()
        assert row is not None
        assert "raw sql visible" in row[0]
        raw_conn.close()
        state.close()

    def test_decision_visible_via_raw_sqlite(self, tmp_path: Path):
        db_path = tmp_path / "test.db"
        state = StateManager(db_path)
        state.init_db()
        stream = state.create_stream("Raw SQL Test", ["repo"])
        state.add_decision(stream.id, "raw sql decision", "testing raw visibility")

        raw_conn = sqlite3.connect(str(db_path))
        row = raw_conn.execute(
            "SELECT what FROM decisions WHERE what LIKE '%raw sql decision%'"
        ).fetchone()
        assert row is not None
        raw_conn.close()
        state.close()
