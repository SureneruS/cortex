from cortex.container import Container
from cortex.services.search_service import SearchService
from cortex.services.stream_service import StreamService


class TestSameConnectionVisibility:
    """Entries are immediately visible on the same service instance that wrote them."""

    def test_update_visible_after_add(self, stream_svc: StreamService, search_svc: SearchService):
        stream = stream_svc.create_stream("Test", ["repo"])
        update = stream_svc.add_update(stream.id, "deployed auth module", "Auth deployed")
        results = search_svc.search("auth")
        assert any(r.id == update.id for r in results)

    def test_decision_visible_after_add(self, stream_svc: StreamService, search_svc: SearchService):
        stream = stream_svc.create_stream("Test", ["repo"])
        decision = stream_svc.add_decision(stream.id, "Use JWT", "Stateless auth")
        results = search_svc.search("JWT")
        assert any(r.id == decision.id for r in results)

    def test_update_in_stream_context_after_add(self, stream_svc: StreamService):
        stream = stream_svc.create_stream("Test", ["repo"])
        stream_svc.add_update(stream.id, "new feature landed", "Feature landed")
        ctx = stream_svc.get_stream_context(stream.id)
        assert len(ctx["updates"]) == 1
        assert ctx["updates"][0]["content"] == "new feature landed"

    def test_decision_in_stream_context_after_add(self, stream_svc: StreamService):
        stream = stream_svc.create_stream("Test", ["repo"])
        stream_svc.add_decision(stream.id, "Use Redis", "Fast cache")
        ctx = stream_svc.get_stream_context(stream.id)
        assert len(ctx["decisions"]) == 1
        assert ctx["decisions"][0]["what"] == "Use Redis"

    def test_multiple_writes_all_visible(self, stream_svc: StreamService, search_svc: SearchService):
        stream = stream_svc.create_stream("Test", ["repo"])
        for i in range(5):
            stream_svc.add_update(stream.id, f"update {i} about testing", f"Test {i}")
        results = search_svc.search("testing")
        assert len(results) == 5


class TestCrossInstanceVisibility:
    """Entries written by one Container are visible to a second (same DB)."""

    def test_update_visible_from_second_instance(self, mongo_db):
        writer = Container(mongo_db)
        stream = writer.stream_service.create_stream("Test", ["repo"])
        writer.stream_service.add_update(stream.id, "cross-instance content", "Cross-inst update")

        reader = Container(mongo_db)
        ctx = reader.stream_service.get_stream_context(stream.id)
        assert len(ctx["updates"]) == 1
        assert ctx["updates"][0]["content"] == "cross-instance content"

    def test_stream_visible_from_second_instance(self, mongo_db):
        writer = Container(mongo_db)
        stream = writer.stream_service.create_stream("Visible Stream", ["repo"])

        reader = Container(mongo_db)
        found = reader.stream_service.get_stream(stream.id)
        assert found is not None
        assert found.title == "Visible Stream"


class TestWriteThenRead:
    """Writes are immediately queryable via reads."""

    def test_log_update_then_search(self, stream_svc: StreamService, search_svc: SearchService):
        stream = stream_svc.create_stream("Test", ["repo"])
        update = stream_svc.add_update(stream.id, "deployed new service", "Service deployed")
        assert update.id
        results = search_svc.search("deployed")
        assert len(results) >= 1
        assert any("deployed" in getattr(r, "content", "") for r in results)

    def test_log_decision_then_search(self, stream_svc: StreamService, search_svc: SearchService):
        stream = stream_svc.create_stream("Test", ["repo"])
        decision = stream_svc.add_decision(stream.id, "Use PostgreSQL", "ACID compliance needed")
        assert decision.id
        results = search_svc.search("PostgreSQL")
        assert len(results) >= 1

    def test_log_update_then_get_context(self, stream_svc: StreamService):
        stream = stream_svc.create_stream("Test", ["repo"])
        stream_svc.add_update(stream.id, "context visible content", "Context test")
        ctx = stream_svc.get_stream_context(stream.id)
        assert len(ctx["updates"]) >= 1
