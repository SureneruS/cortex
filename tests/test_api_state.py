from cortex.services.stream_service import StreamService


def test_unlink_session(stream_svc: StreamService):
    stream = stream_svc.create_stream("Test", ["repo"])
    stream_svc.link_session("sess-001", stream.id, repo="repo")
    sessions_before = stream_svc.get_stream_context(stream.id)["sessions"]
    assert len(sessions_before) == 1

    stream_svc.unlink_session("sess-001", stream.id)
    sessions_after = stream_svc.get_stream_context(stream.id)["sessions"]
    assert len(sessions_after) == 0


def test_unlink_session_nonexistent(stream_svc: StreamService):
    stream = stream_svc.create_stream("Test", ["repo"])
    stream_svc.unlink_session("nonexistent", stream.id)  # should not raise


def test_move_session(stream_svc: StreamService):
    s1 = stream_svc.create_stream("Stream A", ["repo"])
    s2 = stream_svc.create_stream("Stream B", ["repo"])
    stream_svc.link_session("sess-001", s1.id, repo="repo")

    stream_svc.move_session("sess-001", s1.id, s2.id)

    ctx1 = stream_svc.get_stream_context(s1.id)
    ctx2 = stream_svc.get_stream_context(s2.id)
    assert len(ctx1["sessions"]) == 0
    assert len(ctx2["sessions"]) == 1
    assert ctx2["sessions"][0]["session_id"] == "sess-001"


def test_get_recent_activity(stream_svc: StreamService):
    s1 = stream_svc.create_stream("Stream A", ["repo"])
    s2 = stream_svc.create_stream("Stream B", ["repo"])
    stream_svc.add_update(s1.id, "First update", "First")
    stream_svc.add_decision(s2.id, "Some decision", "Because")
    stream_svc.add_update(s1.id, "Second update", "Second")

    activity = stream_svc.get_recent_activity(limit=10)
    assert len(activity) == 3
    # Most recent first
    assert activity[0]["summary"] == "Second"
    assert activity[0]["type"] == "update"
    assert activity[0]["stream_id"] == s1.id
    # Decisions included
    types = {a["type"] for a in activity}
    assert "decision" in types
