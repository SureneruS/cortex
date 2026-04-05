from cortex.services.stream_service import StreamService


class TestListStreams:
    def test_list_active_only(self, stream_svc: StreamService):
        s1 = stream_svc.create_stream("Active", ["repo"])
        s2 = stream_svc.create_stream("Done", ["repo"])
        stream_svc.complete_stream(s2.id, "done")
        results = stream_svc.list_streams("active")
        assert len(results) == 1
        assert results[0].id == s1.id

    def test_list_completed_only(self, stream_svc: StreamService):
        stream_svc.create_stream("Active", ["repo"])
        s2 = stream_svc.create_stream("Done", ["repo"])
        stream_svc.complete_stream(s2.id, "done")
        results = stream_svc.list_streams("completed")
        assert len(results) == 1
        assert results[0].id == s2.id

    def test_list_paused_only(self, stream_svc: StreamService):
        stream_svc.create_stream("Active", ["repo"])
        s2 = stream_svc.create_stream("Paused", ["repo"])
        stream_svc.update_stream(s2.id, status="paused")
        results = stream_svc.list_streams("paused")
        assert len(results) == 1
        assert results[0].id == s2.id

    def test_list_all(self, stream_svc: StreamService):
        stream_svc.create_stream("Active", ["repo"])
        s2 = stream_svc.create_stream("Done", ["repo"])
        stream_svc.complete_stream(s2.id, "done")
        s3 = stream_svc.create_stream("Paused", ["repo"])
        stream_svc.update_stream(s3.id, status="paused")
        results = stream_svc.list_streams("all")
        assert len(results) == 3

    def test_get_active_streams_uses_list_streams(self, stream_svc: StreamService):
        s1 = stream_svc.create_stream("Active", ["repo"])
        s2 = stream_svc.create_stream("Done", ["repo"])
        stream_svc.complete_stream(s2.id, "done")
        active = stream_svc.get_active_streams()
        assert len(active) == 1
        assert active[0].id == s1.id
