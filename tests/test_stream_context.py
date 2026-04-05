from cortex.services.stream_service import StreamService


class TestGetStreamContext:
    def test_returns_updates_and_decisions(self, stream_svc: StreamService):
        s = stream_svc.create_stream("Test", ["repo"])
        stream_svc.add_update(s.id, "Update content", "Update summary")
        stream_svc.add_decision(s.id, "Decided X", "Because Y")
        ctx = stream_svc.get_stream_context(s.id)
        assert len(ctx["updates"]) == 1
        assert len(ctx["decisions"]) == 1

    def test_returns_empty_for_missing_stream(self, stream_svc: StreamService):
        ctx = stream_svc.get_stream_context("nonexistent")
        assert ctx == {}

    def test_includes_stream_metadata(self, stream_svc: StreamService):
        s = stream_svc.create_stream("Test", ["repo"], metadata={"tags": ["feature"]})
        ctx = stream_svc.get_stream_context(s.id)
        assert ctx["stream"]["metadata"] == {"tags": ["feature"]}

    def test_newest_first_order(self, stream_svc: StreamService):
        s = stream_svc.create_stream("Test", ["repo"])
        stream_svc.add_update(s.id, "First", "First update")
        stream_svc.add_update(s.id, "Second", "Second update")
        ctx = stream_svc.get_stream_context(s.id)
        assert ctx["updates"][0]["summary"] == "Second update"
        assert ctx["updates"][1]["summary"] == "First update"
