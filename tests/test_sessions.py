from cortex.mongo_state import MongoStateManager


class TestLinkSession:
    def test_links_session_to_stream(self, state: MongoStateManager):
        s = state.create_stream("Test", ["repo"])
        state.link_session("session-1", s.id)
        stream_ids = state.get_streams_for_session("session-1")
        assert stream_ids == [s.id]

    def test_multiple_streams_per_session(self, state: MongoStateManager):
        s1 = state.create_stream("Stream 1", ["repo"])
        s2 = state.create_stream("Stream 2", ["repo"])
        state.link_session("session-1", s1.id)
        state.link_session("session-1", s2.id)
        stream_ids = state.get_streams_for_session("session-1")
        assert set(stream_ids) == {s1.id, s2.id}

    def test_duplicate_link_is_idempotent(self, state: MongoStateManager):
        s = state.create_stream("Test", ["repo"])
        state.link_session("session-1", s.id)
        state.link_session("session-1", s.id)
        stream_ids = state.get_streams_for_session("session-1")
        assert stream_ids == [s.id]

    def test_unknown_session_returns_empty(self, state: MongoStateManager):
        assert state.get_streams_for_session("nonexistent") == []
