from cortex.adapters.vector_store import SqliteVectorStore
from cortex.container import Container
from cortex.domain.models import Decision, Update
from cortex.services.search_service import SearchService
from cortex.services.stream_service import StreamService


class TestVecIndexLifecycle:
    def test_write_queues_to_pending(self, stream_svc: StreamService, vec_store: SqliteVectorStore):
        stream = stream_svc.create_stream("Test", ["repo"])
        stream_svc.add_update(stream.id, "Deployed OAuth2 auth module", "Auth deployment")
        pending = vec_store._conn.execute("SELECT COUNT(*) FROM vec_pending").fetchone()[0]
        vec_map = vec_store._conn.execute("SELECT COUNT(*) FROM vec_map").fetchone()[0]
        assert pending == 1
        assert vec_map == 0  # not eagerly embedded

    def test_flush_moves_pending_to_vec_index(self, stream_svc: StreamService, vec_store: SqliteVectorStore):
        stream = stream_svc.create_stream("Test", ["repo"])
        stream_svc.add_update(stream.id, "Deployed OAuth2 auth module", "Auth deployment")
        vec_store._flush_pending()
        pending = vec_store._conn.execute("SELECT COUNT(*) FROM vec_pending").fetchone()[0]
        vec_map = vec_store._conn.execute("SELECT COUNT(*) FROM vec_map").fetchone()[0]
        assert pending == 0
        assert vec_map == 1

    def test_search_triggers_flush(self, stream_svc: StreamService, vec_store: SqliteVectorStore):
        stream = stream_svc.create_stream("Test", ["repo"])
        stream_svc.add_update(stream.id, "Deployed OAuth2 auth module", "Auth deployment")
        vec_store.search("OAuth2")
        pending = vec_store._conn.execute("SELECT COUNT(*) FROM vec_pending").fetchone()[0]
        assert pending == 0

    def test_vec_deindex_removes_pending(self, stream_svc: StreamService, vec_store: SqliteVectorStore):
        stream = stream_svc.create_stream("Test", ["repo"])
        update = stream_svc.add_update(stream.id, "Some content", "Summary")
        assert vec_store._conn.execute("SELECT COUNT(*) FROM vec_pending").fetchone()[0] == 1
        stream_svc.delete_update(update.id)
        assert vec_store._conn.execute("SELECT COUNT(*) FROM vec_pending").fetchone()[0] == 0

    def test_vec_deindex_removes_flushed(self, stream_svc: StreamService, vec_store: SqliteVectorStore):
        stream = stream_svc.create_stream("Test", ["repo"])
        update = stream_svc.add_update(stream.id, "Some content", "Summary")
        vec_store._flush_pending()
        assert vec_store._conn.execute("SELECT COUNT(*) FROM vec_map").fetchone()[0] == 1
        stream_svc.delete_update(update.id)
        assert vec_store._conn.execute("SELECT COUNT(*) FROM vec_map").fetchone()[0] == 0

    def test_edit_update_requeues_pending(self, stream_svc: StreamService, vec_store: SqliteVectorStore):
        stream = stream_svc.create_stream("Test", ["repo"])
        update = stream_svc.add_update(stream.id, "Old content", "Old summary")
        vec_store._flush_pending()
        assert vec_store._conn.execute("SELECT COUNT(*) FROM vec_map").fetchone()[0] == 1
        stream_svc.edit_update(update.id, content="New content", summary="New summary")
        # Old entry removed from vec_map, new entry in pending
        assert vec_store._conn.execute("SELECT COUNT(*) FROM vec_pending").fetchone()[0] == 1


class TestVecSearch:
    def test_vec_search_returns_results(self, populated_container: Container):
        results = populated_container.vector_store.search("docker container setup")
        assert len(results) >= 1
        assert all(len(r) == 3 for r in results)

    def test_semantic_search_finds_content(self, populated_container: Container):
        results = populated_container.search_service.search("docker")
        assert len(results) >= 1

    def test_search_returns_typed_entities(self, populated_container: Container):
        results = populated_container.search_service.search("WAL concurrent")
        assert any(isinstance(r, (Update, Decision)) for r in results)


class TestReindex:
    def test_reindex_populates_from_scratch(self, populated_container: Container):
        svc = populated_container.stream_service
        vec = populated_container.vector_store
        svc.clear_indexes()
        assert vec._conn.execute("SELECT COUNT(*) FROM vec_map").fetchone()[0] == 0
        svc.rebuild_vec_index()
        assert vec._conn.execute("SELECT COUNT(*) FROM vec_map").fetchone()[0] >= 4

    def test_clear_indexes_empties_vec_and_pending(self, populated_container: Container):
        svc = populated_container.stream_service
        vec = populated_container.vector_store
        svc.clear_indexes()
        vec_count = vec._conn.execute("SELECT COUNT(*) FROM vec_map").fetchone()[0]
        pending_count = vec._conn.execute("SELECT COUNT(*) FROM vec_pending").fetchone()[0]
        assert vec_count == 0
        assert pending_count == 0


class TestHybridFallback:
    def test_text_search_for_exact_keyword(self, stream_svc: StreamService, search_svc: SearchService):
        stream = stream_svc.create_stream("Test", ["repo"])
        stream_svc.add_update(stream.id, "Fixed bug ATS-1234 in login flow", "ATS-1234 fix")
        results = search_svc.search("ATS-1234")
        assert len(results) >= 1
        assert any(isinstance(r, Update) and "ATS-1234" in r.content for r in results)
