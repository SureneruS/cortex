from cortex.state import StateManager


def test_unlink_session(state: StateManager):
    stream = state.create_stream("Test", ["repo"])
    state.link_session("sess-001", stream.id, repo="repo")
    sessions_before = state.get_stream_context(stream.id)["sessions"]
    assert len(sessions_before) == 1

    state.unlink_session("sess-001", stream.id)
    sessions_after = state.get_stream_context(stream.id)["sessions"]
    assert len(sessions_after) == 0


def test_unlink_session_nonexistent(state: StateManager):
    stream = state.create_stream("Test", ["repo"])
    state.unlink_session("nonexistent", stream.id)  # should not raise


def test_move_session(state: StateManager):
    s1 = state.create_stream("Stream A", ["repo"])
    s2 = state.create_stream("Stream B", ["repo"])
    state.link_session("sess-001", s1.id, repo="repo")

    state.move_session("sess-001", s1.id, s2.id)

    ctx1 = state.get_stream_context(s1.id)
    ctx2 = state.get_stream_context(s2.id)
    assert len(ctx1["sessions"]) == 0
    assert len(ctx2["sessions"]) == 1
    assert ctx2["sessions"][0]["session_id"] == "sess-001"


def test_get_recent_activity(state: StateManager):
    s1 = state.create_stream("Stream A", ["repo"])
    s2 = state.create_stream("Stream B", ["repo"])
    state.add_update(s1.id, "First update", "First")
    state.add_decision(s2.id, "Some decision", "Because")
    state.add_update(s1.id, "Second update", "Second")

    activity = state.get_recent_activity(limit=10)
    assert len(activity) == 3
    # Most recent first
    assert activity[0]["summary"] == "Second"
    assert activity[0]["type"] == "update"
    assert activity[0]["stream_id"] == s1.id
    # Decisions included
    types = {a["type"] for a in activity}
    assert "decision" in types
