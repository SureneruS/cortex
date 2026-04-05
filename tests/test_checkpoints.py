from cortex.domain.models import Checkpoint
from cortex.services.search_service import SearchService
from cortex.services.stream_service import StreamService


class TestSaveCheckpoint:
    def test_creates_checkpoint(self, stream_svc: StreamService):
        cp = stream_svc.save_checkpoint("2026-03-02", "Week content")
        assert cp.week_of == "2026-03-02"
        assert cp.content == "Week content"

    def test_auto_captures_active_streams(self, stream_svc: StreamService):
        s1 = stream_svc.create_stream("Stream A", ["repo-a"])
        s2 = stream_svc.create_stream("Stream B", ["repo-b"])
        cp = stream_svc.save_checkpoint("2026-03-02", "content")
        assert s1.id in cp.stream_ids
        assert s2.id in cp.stream_ids

    def test_explicit_stream_ids(self, stream_svc: StreamService):
        stream_svc.create_stream("Stream A", ["repo-a"])
        cp = stream_svc.save_checkpoint("2026-03-02", "content", stream_ids=["custom-id"])
        assert cp.stream_ids == ["custom-id"]

    def test_upserts_on_same_week(self, stream_svc: StreamService):
        cp1 = stream_svc.save_checkpoint("2026-03-02", "Original")
        cp2 = stream_svc.save_checkpoint("2026-03-02", "Updated")
        assert cp1.id == cp2.id
        assert cp2.content == "Updated"

    def test_upsert_preserves_id(self, stream_svc: StreamService):
        cp1 = stream_svc.save_checkpoint("2026-03-02", "v1")
        cp2 = stream_svc.save_checkpoint("2026-03-02", "v2")
        assert cp1.id == cp2.id

    def test_different_weeks_create_separate(self, stream_svc: StreamService):
        cp1 = stream_svc.save_checkpoint("2026-03-02", "Week 1")
        cp2 = stream_svc.save_checkpoint("2026-03-09", "Week 2")
        assert cp1.id != cp2.id

    def test_metadata_stored(self, stream_svc: StreamService):
        cp = stream_svc.save_checkpoint("2026-03-02", "content", metadata={"type": "wrapup"})
        assert cp.metadata == {"type": "wrapup"}

    def test_excludes_non_active_streams(self, stream_svc: StreamService):
        s1 = stream_svc.create_stream("Active", ["repo"])
        s2 = stream_svc.create_stream("Completed", ["repo"])
        stream_svc.complete_stream(s2.id, "done")
        cp = stream_svc.save_checkpoint("2026-03-02", "content")
        assert s1.id in cp.stream_ids
        assert s2.id not in cp.stream_ids


class TestGetCheckpoint:
    def test_get_latest(self, stream_svc: StreamService):
        stream_svc.save_checkpoint("2026-03-02", "Week 1")
        stream_svc.save_checkpoint("2026-03-09", "Week 2")
        latest = stream_svc.get_checkpoint()
        assert latest.week_of == "2026-03-09"

    def test_get_specific_week(self, stream_svc: StreamService):
        stream_svc.save_checkpoint("2026-03-02", "Week 1")
        stream_svc.save_checkpoint("2026-03-09", "Week 2")
        cp = stream_svc.get_checkpoint("2026-03-02")
        assert cp.content == "Week 1"

    def test_returns_none_when_empty(self, stream_svc: StreamService):
        assert stream_svc.get_checkpoint() is None

    def test_returns_none_for_missing_week(self, stream_svc: StreamService):
        stream_svc.save_checkpoint("2026-03-02", "content")
        assert stream_svc.get_checkpoint("2099-01-01") is None


class TestCheckpointSearch:
    def test_checkpoint_found_in_search(self, stream_svc: StreamService, search_svc: SearchService):
        stream_svc.save_checkpoint("2026-03-02", "Shadow roles shipped to production")
        results = search_svc.search("shadow")
        assert len(results) >= 1
        assert any(isinstance(r, Checkpoint) for r in results)

    def test_checkpoint_not_found_for_unrelated_query(self, stream_svc: StreamService, search_svc: SearchService):
        stream_svc.save_checkpoint("2026-03-02", "Shadow roles shipped")
        results = search_svc.search("kubernetes")
        assert not any(isinstance(r, Checkpoint) for r in results)
