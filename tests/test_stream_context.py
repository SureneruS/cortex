from cortex.state import StateManager


class TestGetStreamContext:
    def test_returns_updates_and_decisions(self, state: StateManager):
        s = state.create_stream("Test", ["repo"])
        state.add_update(s.id, "Update content", "Update summary")
        state.add_decision(s.id, "Decided X", "Because Y")
        ctx = state.get_stream_context(s.id)
        assert len(ctx["updates"]) == 1
        assert len(ctx["decisions"]) == 1

    def test_returns_empty_for_missing_stream(self, state: StateManager):
        ctx = state.get_stream_context("nonexistent")
        assert ctx == {}

    def test_includes_stream_metadata(self, state: StateManager):
        s = state.create_stream("Test", ["repo"], metadata={"tags": ["feature"]})
        ctx = state.get_stream_context(s.id)
        assert ctx["stream"]["metadata"] == {"tags": ["feature"]}

    def test_newest_first_order(self, state: StateManager):
        s = state.create_stream("Test", ["repo"])
        state.add_update(s.id, "First", "First update")
        state.add_update(s.id, "Second", "Second update")
        ctx = state.get_stream_context(s.id)
        assert ctx["updates"][0]["summary"] == "Second update"
        assert ctx["updates"][1]["summary"] == "First update"
