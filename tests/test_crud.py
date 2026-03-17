from cortex.state import StateManager


class TestEditUpdate:
    def test_edit_content(self, state: StateManager):
        s = state.create_stream("Test", ["repo"])
        u = state.add_update(s.id, "Original content", "Original summary")
        edited = state.edit_update(u.id, content="New content")
        assert edited.content == "New content"
        assert edited.summary == "Original summary"

    def test_edit_summary(self, state: StateManager):
        s = state.create_stream("Test", ["repo"])
        u = state.add_update(s.id, "Content", "Old summary")
        edited = state.edit_update(u.id, summary="New summary")
        assert edited.summary == "New summary"
        assert edited.content == "Content"

    def test_edit_metadata(self, state: StateManager):
        s = state.create_stream("Test", ["repo"])
        u = state.add_update(s.id, "Content", "Summary", metadata={"a": 1})
        edited = state.edit_update(u.id, metadata={"b": 2})
        assert edited.metadata == {"b": 2}

    def test_edit_nonexistent_returns_none(self, state: StateManager):
        assert state.edit_update("nonexistent") is None

    def test_no_changes_returns_original(self, state: StateManager):
        s = state.create_stream("Test", ["repo"])
        u = state.add_update(s.id, "Content", "Summary")
        result = state.edit_update(u.id)
        assert result.content == "Content"

    def test_edit_updates_search_index(self, state: StateManager):
        s = state.create_stream("Test", ["repo"])
        u = state.add_update(s.id, "alpha bravo", "alpha bravo")
        state.edit_update(u.id, content="charlie delta", summary="charlie delta")
        assert any(r.id == u.id for r in state.search("charlie"))
        assert not any(r.id == u.id for r in state.search("alpha"))


class TestEditDecision:
    def test_edit_what(self, state: StateManager):
        s = state.create_stream("Test", ["repo"])
        d = state.add_decision(s.id, "Old what", "Old why")
        edited = state.edit_decision(d.id, what="New what")
        assert edited.what == "New what"
        assert edited.why == "Old why"

    def test_edit_why(self, state: StateManager):
        s = state.create_stream("Test", ["repo"])
        d = state.add_decision(s.id, "What", "Old why")
        edited = state.edit_decision(d.id, why="New why")
        assert edited.why == "New why"

    def test_edit_nonexistent_returns_none(self, state: StateManager):
        assert state.edit_decision("nonexistent") is None

    def test_edit_updates_search_index(self, state: StateManager):
        s = state.create_stream("Test", ["repo"])
        d = state.add_decision(s.id, "alpha", "bravo")
        state.edit_decision(d.id, what="charlie", why="delta")
        assert any(r.id == d.id for r in state.search("charlie"))
        assert not any(r.id == d.id for r in state.search("alpha"))


class TestDeleteStream:
    def test_deletes_stream(self, state: StateManager):
        s = state.create_stream("Test", ["repo"])
        state.delete_stream(s.id)
        assert state.get_stream(s.id) is None

    def test_cascades_updates(self, state: StateManager):
        s = state.create_stream("Test", ["repo"])
        state.add_update(s.id, "Content", "Summary")
        state.delete_stream(s.id)
        ctx = state.get_stream_context(s.id)
        assert ctx == {}

    def test_cascades_decisions(self, state: StateManager):
        s = state.create_stream("Test", ["repo"])
        state.add_decision(s.id, "What", "Why")
        state.delete_stream(s.id)
        ctx = state.get_stream_context(s.id)
        assert ctx == {}

    def test_deindexes_entries(self, state: StateManager):
        s = state.create_stream("Test", ["repo"])
        state.add_update(s.id, "unique_xyzzy_token", "unique_xyzzy_token")
        state.delete_stream(s.id)
        assert len(state.search("unique_xyzzy_token")) == 0

    def test_delete_nonexistent_is_safe(self, state: StateManager):
        state.delete_stream("nonexistent")
