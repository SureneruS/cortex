import pytest

from cortex.domain.models import Decision, Update
from cortex.mongo_state import MongoStateManager


class TestVecIndexLifecycle:
    def test_write_queues_to_pending(self, state: MongoStateManager):
        stream = state.create_stream("Test", ["repo"])
        state.add_update(stream.id, "Deployed OAuth2 auth module", "Auth deployment")
        pending = state._conn.execute("SELECT COUNT(*) FROM vec_pending").fetchone()[0]
        vec_map = state._conn.execute("SELECT COUNT(*) FROM vec_map").fetchone()[0]
        assert pending == 1
        assert vec_map == 0  # not eagerly embedded

    def test_flush_moves_pending_to_vec_index(self, state: MongoStateManager):
        stream = state.create_stream("Test", ["repo"])
        state.add_update(stream.id, "Deployed OAuth2 auth module", "Auth deployment")
        state._flush_pending()
        pending = state._conn.execute("SELECT COUNT(*) FROM vec_pending").fetchone()[0]
        vec_map = state._conn.execute("SELECT COUNT(*) FROM vec_map").fetchone()[0]
        assert pending == 0
        assert vec_map == 1

    def test_search_triggers_flush(self, state: MongoStateManager):
        stream = state.create_stream("Test", ["repo"])
        state.add_update(stream.id, "Deployed OAuth2 auth module", "Auth deployment")
        state._vec_search("OAuth2")
        pending = state._conn.execute("SELECT COUNT(*) FROM vec_pending").fetchone()[0]
        assert pending == 0

    def test_vec_deindex_removes_pending(self, state: MongoStateManager):
        stream = state.create_stream("Test", ["repo"])
        update = state.add_update(stream.id, "Some content", "Summary")
        assert state._conn.execute("SELECT COUNT(*) FROM vec_pending").fetchone()[0] == 1
        state.delete_update(update.id)
        assert state._conn.execute("SELECT COUNT(*) FROM vec_pending").fetchone()[0] == 0

    def test_vec_deindex_removes_flushed(self, state: MongoStateManager):
        stream = state.create_stream("Test", ["repo"])
        update = state.add_update(stream.id, "Some content", "Summary")
        state._flush_pending()
        assert state._conn.execute("SELECT COUNT(*) FROM vec_map").fetchone()[0] == 1
        state.delete_update(update.id)
        assert state._conn.execute("SELECT COUNT(*) FROM vec_map").fetchone()[0] == 0

    def test_edit_update_requeues_pending(self, state: MongoStateManager):
        stream = state.create_stream("Test", ["repo"])
        update = state.add_update(stream.id, "Old content", "Old summary")
        state._flush_pending()
        assert state._conn.execute("SELECT COUNT(*) FROM vec_map").fetchone()[0] == 1
        state.edit_update(update.id, content="New content", summary="New summary")
        # Old entry removed from vec_map, new entry in pending
        assert state._conn.execute("SELECT COUNT(*) FROM vec_pending").fetchone()[0] == 1


class TestVecSearch:
    def test_vec_search_returns_results(self, populated_state: MongoStateManager):
        results = populated_state._vec_search("docker container setup")
        assert len(results) >= 1
        assert all(len(r) == 3 for r in results)

    def test_semantic_search_finds_content(self, populated_state: MongoStateManager):
        results = populated_state.search("docker")
        assert len(results) >= 1

    def test_search_returns_typed_entities(self, populated_state: MongoStateManager):
        results = populated_state.search("WAL concurrent")
        assert any(isinstance(r, (Update, Decision)) for r in results)


class TestReindex:
    def test_reindex_populates_from_scratch(self, populated_state: MongoStateManager):
        populated_state.clear_indexes()
        assert populated_state._conn.execute("SELECT COUNT(*) FROM vec_map").fetchone()[0] == 0
        populated_state._rebuild_vec_index()
        assert populated_state._conn.execute("SELECT COUNT(*) FROM vec_map").fetchone()[0] >= 4

    def test_clear_indexes_empties_vec_and_pending(self, populated_state: MongoStateManager):
        populated_state.clear_indexes()
        vec_count = populated_state._conn.execute("SELECT COUNT(*) FROM vec_map").fetchone()[0]
        pending_count = populated_state._conn.execute("SELECT COUNT(*) FROM vec_pending").fetchone()[0]
        assert vec_count == 0
        assert pending_count == 0


class TestHybridFallback:
    def test_text_search_for_exact_keyword(self, state: MongoStateManager):
        stream = state.create_stream("Test", ["repo"])
        state.add_update(stream.id, "Fixed bug ATS-1234 in login flow", "ATS-1234 fix")
        results = state.search("ATS-1234")
        assert len(results) >= 1
        assert any(isinstance(r, Update) and "ATS-1234" in r.content for r in results)
