from cortex.services.stream_service import StreamService


class TestLinkSession:
    def test_links_session_to_stream(self, stream_svc: StreamService):
        s = stream_svc.create_stream("Test", ["repo"])
        stream_svc.link_session("session-1", s.id)
        stream_ids = stream_svc.get_streams_for_session("session-1")
        assert stream_ids == [s.id]

    def test_multiple_streams_per_session(self, stream_svc: StreamService):
        s1 = stream_svc.create_stream("Stream 1", ["repo"])
        s2 = stream_svc.create_stream("Stream 2", ["repo"])
        stream_svc.link_session("session-1", s1.id)
        stream_svc.link_session("session-1", s2.id)
        stream_ids = stream_svc.get_streams_for_session("session-1")
        assert set(stream_ids) == {s1.id, s2.id}

    def test_duplicate_link_is_idempotent(self, stream_svc: StreamService):
        s = stream_svc.create_stream("Test", ["repo"])
        stream_svc.link_session("session-1", s.id)
        stream_svc.link_session("session-1", s.id)
        stream_ids = stream_svc.get_streams_for_session("session-1")
        assert stream_ids == [s.id]

    def test_unknown_session_returns_empty(self, stream_svc: StreamService):
        assert stream_svc.get_streams_for_session("nonexistent") == []
