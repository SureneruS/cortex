import pytest

from cortex.models import Decision, Update
from cortex.mongo_state import MongoStateManager


class TestVecIndexLifecycle:
    def test_vec_index_populated_on_add_update(self, state: MongoStateManager):
        stream = state.create_stream("Test", ["repo"])
        state.add_update(stream.id, "Deployed OAuth2 auth module", "Auth deployment")
        count = state._conn.execute("SELECT COUNT(*) FROM vec_map").fetchone()[0]
        assert count == 1

    def test_vec_index_populated_on_add_decision(self, state: MongoStateManager):
        stream = state.create_stream("Test", ["repo"])
        state.add_decision(stream.id, "Use WAL mode", "Better concurrency")
        count = state._conn.execute("SELECT COUNT(*) FROM vec_map").fetchone()[0]
        assert count == 1

    def test_vec_deindex_on_delete_update(self, state: MongoStateManager):
        stream = state.create_stream("Test", ["repo"])
        update = state.add_update(stream.id, "Some content", "Summary")
        assert state._conn.execute("SELECT COUNT(*) FROM vec_map").fetchone()[0] == 1
        state.delete_update(update.id)
        assert state._conn.execute("SELECT COUNT(*) FROM vec_map").fetchone()[0] == 0

    def test_vec_deindex_on_delete_decision(self, state: MongoStateManager):
        stream = state.create_stream("Test", ["repo"])
        decision = state.add_decision(stream.id, "What", "Why")
        assert state._conn.execute("SELECT COUNT(*) FROM vec_map").fetchone()[0] == 1
        state.delete_decision(decision.id)
        assert state._conn.execute("SELECT COUNT(*) FROM vec_map").fetchone()[0] == 0

    def test_edit_update_reindexes_vec(self, state: MongoStateManager):
        stream = state.create_stream("Test", ["repo"])
        update = state.add_update(stream.id, "Old content", "Old summary")
        old_rowid = state._conn.execute(
            "SELECT vec_rowid FROM vec_map WHERE entity_id = ?", (update.id,)
        ).fetchone()[0]
        state.edit_update(update.id, content="New content", summary="New summary")
        new_rowid = state._conn.execute(
            "SELECT vec_rowid FROM vec_map WHERE entity_id = ?", (update.id,)
        ).fetchone()[0]
        assert old_rowid != new_rowid


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

    def test_clear_indexes_empties_vec(self, populated_state: MongoStateManager):
        populated_state.clear_indexes()
        vec_count = populated_state._conn.execute("SELECT COUNT(*) FROM vec_map").fetchone()[0]
        assert vec_count == 0


class TestHybridFallback:
    def test_text_search_for_exact_keyword(self, state: MongoStateManager):
        stream = state.create_stream("Test", ["repo"])
        state.add_update(stream.id, "Fixed bug ATS-1234 in login flow", "ATS-1234 fix")
        results = state.search("ATS-1234")
        assert len(results) >= 1
        assert any(isinstance(r, Update) and "ATS-1234" in r.content for r in results)
