from cortex.services.search_service import SearchService
from cortex.services.stream_service import StreamService


class TestEditUpdate:
    def test_edit_content(self, stream_svc: StreamService):
        s = stream_svc.create_stream("Test", ["repo"])
        u = stream_svc.add_update(s.id, "Original content", "Original summary")
        edited = stream_svc.edit_update(u.id, content="New content")
        assert edited.content == "New content"
        assert edited.summary == "Original summary"

    def test_edit_summary(self, stream_svc: StreamService):
        s = stream_svc.create_stream("Test", ["repo"])
        u = stream_svc.add_update(s.id, "Content", "Old summary")
        edited = stream_svc.edit_update(u.id, summary="New summary")
        assert edited.summary == "New summary"
        assert edited.content == "Content"

    def test_edit_metadata(self, stream_svc: StreamService):
        s = stream_svc.create_stream("Test", ["repo"])
        u = stream_svc.add_update(s.id, "Content", "Summary", metadata={"a": 1})
        edited = stream_svc.edit_update(u.id, metadata={"b": 2})
        assert edited.metadata == {"b": 2}

    def test_edit_nonexistent_returns_none(self, stream_svc: StreamService):
        assert stream_svc.edit_update("nonexistent") is None

    def test_no_changes_returns_original(self, stream_svc: StreamService):
        s = stream_svc.create_stream("Test", ["repo"])
        u = stream_svc.add_update(s.id, "Content", "Summary")
        result = stream_svc.edit_update(u.id)
        assert result.content == "Content"

    def test_edit_updates_search_index(self, stream_svc: StreamService, search_svc: SearchService):
        s = stream_svc.create_stream("Test", ["repo"])
        u = stream_svc.add_update(s.id, "alpha bravo", "alpha bravo")
        stream_svc.edit_update(u.id, content="charlie delta", summary="charlie delta")
        assert any(r.id == u.id for r in search_svc.search("charlie"))
        assert not any(r.id == u.id for r in search_svc.search("alpha"))


class TestEditDecision:
    def test_edit_what(self, stream_svc: StreamService):
        s = stream_svc.create_stream("Test", ["repo"])
        d = stream_svc.add_decision(s.id, "Old what", "Old why")
        edited = stream_svc.edit_decision(d.id, what="New what")
        assert edited.what == "New what"
        assert edited.why == "Old why"

    def test_edit_why(self, stream_svc: StreamService):
        s = stream_svc.create_stream("Test", ["repo"])
        d = stream_svc.add_decision(s.id, "What", "Old why")
        edited = stream_svc.edit_decision(d.id, why="New why")
        assert edited.why == "New why"

    def test_edit_nonexistent_returns_none(self, stream_svc: StreamService):
        assert stream_svc.edit_decision("nonexistent") is None

    def test_edit_updates_search_index(self, stream_svc: StreamService, search_svc: SearchService):
        s = stream_svc.create_stream("Test", ["repo"])
        d = stream_svc.add_decision(s.id, "alpha", "bravo")
        stream_svc.edit_decision(d.id, what="charlie", why="delta")
        assert any(r.id == d.id for r in search_svc.search("charlie"))
        assert not any(r.id == d.id for r in search_svc.search("alpha"))


class TestDeleteStream:
    def test_deletes_stream(self, stream_svc: StreamService):
        s = stream_svc.create_stream("Test", ["repo"])
        stream_svc.delete_stream(s.id)
        assert stream_svc.get_stream(s.id) is None

    def test_cascades_updates(self, stream_svc: StreamService):
        s = stream_svc.create_stream("Test", ["repo"])
        stream_svc.add_update(s.id, "Content", "Summary")
        stream_svc.delete_stream(s.id)
        ctx = stream_svc.get_stream_context(s.id)
        assert ctx == {}

    def test_cascades_decisions(self, stream_svc: StreamService):
        s = stream_svc.create_stream("Test", ["repo"])
        stream_svc.add_decision(s.id, "What", "Why")
        stream_svc.delete_stream(s.id)
        ctx = stream_svc.get_stream_context(s.id)
        assert ctx == {}

    def test_deindexes_entries(self, stream_svc: StreamService, search_svc: SearchService):
        s = stream_svc.create_stream("Test", ["repo"])
        stream_svc.add_update(s.id, "unique_xyzzy_token", "unique_xyzzy_token")
        stream_svc.delete_stream(s.id)
        assert len(search_svc.search("unique_xyzzy_token")) == 0

    def test_delete_nonexistent_is_safe(self, stream_svc: StreamService):
        stream_svc.delete_stream("nonexistent")
