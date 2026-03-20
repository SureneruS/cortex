from cortex.mongo_state import MongoStateManager


class TestMetadataMerge:
    def test_merge_by_default(self, state: MongoStateManager):
        s = state.create_stream("Test", ["repo"], metadata={"a": 1, "b": 2})
        updated = state.update_stream(s.id, metadata={"c": 3})
        assert updated.metadata == {"a": 1, "b": 2, "c": 3}

    def test_merge_overwrites_existing_keys(self, state: MongoStateManager):
        s = state.create_stream("Test", ["repo"], metadata={"a": 1, "b": 2})
        updated = state.update_stream(s.id, metadata={"a": 99})
        assert updated.metadata == {"a": 99, "b": 2}

    def test_merge_null_removes_key(self, state: MongoStateManager):
        s = state.create_stream("Test", ["repo"], metadata={"a": 1, "b": 2})
        updated = state.update_stream(s.id, metadata={"b": None})
        assert updated.metadata == {"a": 1}

    def test_replace_metadata(self, state: MongoStateManager):
        s = state.create_stream("Test", ["repo"], metadata={"a": 1, "b": 2})
        updated = state.update_stream(s.id, metadata={"c": 3}, merge_metadata=False)
        assert updated.metadata == {"c": 3}

    def test_replace_metadata_clears_old(self, state: MongoStateManager):
        s = state.create_stream("Test", ["repo"], metadata={"a": 1, "b": 2})
        updated = state.update_stream(s.id, metadata={}, merge_metadata=False)
        assert updated.metadata == {}
