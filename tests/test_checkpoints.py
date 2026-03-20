from cortex.models import Checkpoint
from cortex.mongo_state import MongoStateManager


class TestSaveCheckpoint:
    def test_creates_checkpoint(self, state: MongoStateManager):
        cp = state.save_checkpoint("2026-03-02", "Week content")
        assert cp.week_of == "2026-03-02"
        assert cp.content == "Week content"

    def test_auto_captures_active_streams(self, state: MongoStateManager):
        s1 = state.create_stream("Stream A", ["repo-a"])
        s2 = state.create_stream("Stream B", ["repo-b"])
        cp = state.save_checkpoint("2026-03-02", "content")
        assert s1.id in cp.stream_ids
        assert s2.id in cp.stream_ids

    def test_explicit_stream_ids(self, state: MongoStateManager):
        state.create_stream("Stream A", ["repo-a"])
        cp = state.save_checkpoint("2026-03-02", "content", stream_ids=["custom-id"])
        assert cp.stream_ids == ["custom-id"]

    def test_upserts_on_same_week(self, state: MongoStateManager):
        cp1 = state.save_checkpoint("2026-03-02", "Original")
        cp2 = state.save_checkpoint("2026-03-02", "Updated")
        assert cp1.id == cp2.id
        assert cp2.content == "Updated"

    def test_upsert_preserves_id(self, state: MongoStateManager):
        cp1 = state.save_checkpoint("2026-03-02", "v1")
        cp2 = state.save_checkpoint("2026-03-02", "v2")
        assert cp1.id == cp2.id

    def test_different_weeks_create_separate(self, state: MongoStateManager):
        cp1 = state.save_checkpoint("2026-03-02", "Week 1")
        cp2 = state.save_checkpoint("2026-03-09", "Week 2")
        assert cp1.id != cp2.id

    def test_metadata_stored(self, state: MongoStateManager):
        cp = state.save_checkpoint("2026-03-02", "content", metadata={"type": "wrapup"})
        assert cp.metadata == {"type": "wrapup"}

    def test_excludes_non_active_streams(self, state: MongoStateManager):
        s1 = state.create_stream("Active", ["repo"])
        s2 = state.create_stream("Completed", ["repo"])
        state.complete_stream(s2.id, "done")
        cp = state.save_checkpoint("2026-03-02", "content")
        assert s1.id in cp.stream_ids
        assert s2.id not in cp.stream_ids


class TestGetCheckpoint:
    def test_get_latest(self, state: MongoStateManager):
        state.save_checkpoint("2026-03-02", "Week 1")
        state.save_checkpoint("2026-03-09", "Week 2")
        latest = state.get_checkpoint()
        assert latest.week_of == "2026-03-09"

    def test_get_specific_week(self, state: MongoStateManager):
        state.save_checkpoint("2026-03-02", "Week 1")
        state.save_checkpoint("2026-03-09", "Week 2")
        cp = state.get_checkpoint("2026-03-02")
        assert cp.content == "Week 1"

    def test_returns_none_when_empty(self, state: MongoStateManager):
        assert state.get_checkpoint() is None

    def test_returns_none_for_missing_week(self, state: MongoStateManager):
        state.save_checkpoint("2026-03-02", "content")
        assert state.get_checkpoint("2099-01-01") is None


class TestCheckpointSearch:
    def test_checkpoint_found_in_search(self, state: MongoStateManager):
        state.save_checkpoint("2026-03-02", "Shadow roles shipped to production")
        results = state.search("shadow")
        assert len(results) >= 1
        assert any(isinstance(r, Checkpoint) for r in results)

    def test_checkpoint_not_found_for_unrelated_query(self, state: MongoStateManager):
        state.save_checkpoint("2026-03-02", "Shadow roles shipped")
        results = state.search("kubernetes")
        assert not any(isinstance(r, Checkpoint) for r in results)
