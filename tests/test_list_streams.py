from cortex.mongo_state import MongoStateManager


class TestListStreams:
    def test_list_active_only(self, state: MongoStateManager):
        s1 = state.create_stream("Active", ["repo"])
        s2 = state.create_stream("Done", ["repo"])
        state.complete_stream(s2.id, "done")
        results = state.list_streams("active")
        assert len(results) == 1
        assert results[0].id == s1.id

    def test_list_completed_only(self, state: MongoStateManager):
        state.create_stream("Active", ["repo"])
        s2 = state.create_stream("Done", ["repo"])
        state.complete_stream(s2.id, "done")
        results = state.list_streams("completed")
        assert len(results) == 1
        assert results[0].id == s2.id

    def test_list_paused_only(self, state: MongoStateManager):
        state.create_stream("Active", ["repo"])
        s2 = state.create_stream("Paused", ["repo"])
        state.update_stream(s2.id, status="paused")
        results = state.list_streams("paused")
        assert len(results) == 1
        assert results[0].id == s2.id

    def test_list_all(self, state: MongoStateManager):
        state.create_stream("Active", ["repo"])
        s2 = state.create_stream("Done", ["repo"])
        state.complete_stream(s2.id, "done")
        s3 = state.create_stream("Paused", ["repo"])
        state.update_stream(s3.id, status="paused")
        results = state.list_streams("all")
        assert len(results) == 3

    def test_get_active_streams_uses_list_streams(self, state: MongoStateManager):
        s1 = state.create_stream("Active", ["repo"])
        s2 = state.create_stream("Done", ["repo"])
        state.complete_stream(s2.id, "done")
        active = state.get_active_streams()
        assert len(active) == 1
        assert active[0].id == s1.id
