import pytest

from nova.lib.state import NovaState


def test_load_empty_state(tmp_path):
    state_file = tmp_path / "state.json"
    state_file.write_text('{"last_dream_run": null, "sessions": {}}')
    state = NovaState(state_file)
    assert state.last_dream_run is None
    assert state.sessions == {}


def test_register_session(tmp_path):
    state_file = tmp_path / "state.json"
    state_file.write_text('{"last_dream_run": null, "sessions": {}}')
    state = NovaState(state_file)
    state.register_session("abc123", repos=["foo"], transcript_path="/path")
    state.save()
    reloaded = NovaState(state_file)
    assert "abc123" in reloaded.sessions
    assert reloaded.sessions["abc123"]["repos"] == ["foo"]
    assert reloaded.sessions["abc123"]["memory_injected"] is False


def test_mark_injected(tmp_path):
    state_file = tmp_path / "state.json"
    state_file.write_text('{"last_dream_run": null, "sessions": {}}')
    state = NovaState(state_file)
    state.register_session("abc123", repos=["foo"], transcript_path="/path")
    state.mark_injected("abc123", goal="fix OAuth")
    state.save()
    reloaded = NovaState(state_file)
    assert reloaded.sessions["abc123"]["memory_injected"] is True
    assert reloaded.sessions["abc123"]["goal"] == "fix OAuth"


def test_atomic_write(tmp_path):
    """Verify save uses atomic rename (no .tmp file left behind)."""
    state_file = tmp_path / "state.json"
    state_file.write_text('{"last_dream_run": null, "sessions": {}}')
    state = NovaState(state_file)
    state.register_session("abc", repos=["r"], transcript_path="/p")
    state.save()
    assert not (tmp_path / "state.tmp").exists()
    assert state_file.exists()


def test_nonexistent_state_file_raises(tmp_path):
    """Missing state file should raise FileNotFoundError."""
    with pytest.raises(FileNotFoundError, match="nova-setup"):
        NovaState(tmp_path / "missing.json")


def test_malformed_state_file_raises(tmp_path):
    """Malformed JSON should raise ValueError."""
    state_file = tmp_path / "state.json"
    state_file.write_text("not json at all")
    with pytest.raises(ValueError, match="Malformed"):
        NovaState(state_file)


def test_register_session_with_tmux(tmp_path):
    state_file = tmp_path / "state.json"
    state_file.write_text('{"last_dream_run": null, "sessions": {}}')
    state = NovaState(state_file)
    state.register_session(
        "sess1",
        repos=["recruitment-backend"],
        transcript_path="/tmp/t.jsonl",
        tmux_target="sessions:recruitment-backend",
        tmux_window="recruitment-backend",
    )
    assert state.sessions["sess1"]["tmux_target"] == "sessions:recruitment-backend"
    assert state.sessions["sess1"]["tmux_window"] == "recruitment-backend"


def test_set_slack_thread(tmp_path):
    state_file = tmp_path / "state.json"
    state_file.write_text('{"last_dream_run": null, "sessions": {}}')
    state = NovaState(state_file)
    state.register_session("sess1", repos=["rb"], transcript_path="/tmp/t.jsonl")
    state.set_slack_thread("sess1", thread_ts="123.456", channel="D0ABC")
    assert state.sessions["sess1"]["slack_thread_ts"] == "123.456"
    assert state.sessions["sess1"]["slack_channel"] == "D0ABC"


def test_find_session_by_thread(tmp_path):
    state_file = tmp_path / "state.json"
    state_file.write_text('{"last_dream_run": null, "sessions": {}}')
    state = NovaState(state_file)
    state.register_session("sess1", repos=["rb"], transcript_path="/tmp/t.jsonl")
    state.set_slack_thread("sess1", thread_ts="123.456", channel="D0ABC")
    state.save()

    state2 = NovaState(state_file)
    result = state2.find_session_by_thread("123.456")
    assert result is not None
    assert result[0] == "sess1"


def test_find_session_by_thread_not_found(tmp_path):
    state_file = tmp_path / "state.json"
    state_file.write_text('{"last_dream_run": null, "sessions": {}}')
    state = NovaState(state_file)
    assert state.find_session_by_thread("999.999") is None


def test_set_slack_global(tmp_path):
    state_file = tmp_path / "state.json"
    state_file.write_text('{"last_dream_run": null, "sessions": {}}')
    state = NovaState(state_file)
    state.set_slack_config(dm_channel="D0ABC", bot_user_id="U0BOT")
    state.save()

    state2 = NovaState(state_file)
    assert state2.slack_config["dm_channel"] == "D0ABC"
    assert state2.slack_config["bot_user_id"] == "U0BOT"


def test_register_session_with_chain(tmp_path):
    sf = tmp_path / "state.json"
    sf.write_text('{"sessions": {}}')
    state = NovaState(sf)
    state.register_session(
        "s1",
        repos=["repo"],
        transcript_path="/t.jsonl",
        chain_id="chain-abc",
        chain_sequence=1,
    )
    assert state.sessions["s1"]["chain_id"] == "chain-abc"
    assert state.sessions["s1"]["chain_sequence"] == 1
    assert state.sessions["s1"]["parent_session_id"] is None
    assert state.sessions["s1"]["compaction_count"] == 0
    assert state.sessions["s1"]["status"] == "active"


def test_increment_compaction_count(tmp_path):
    sf = tmp_path / "state.json"
    sf.write_text('{"sessions": {}}')
    state = NovaState(sf)
    state.register_session("s1", repos=["r"], transcript_path="/t.jsonl")
    state.increment_compaction("s1")
    state.increment_compaction("s1")
    assert state.sessions["s1"]["compaction_count"] == 2


def test_set_session_status(tmp_path):
    sf = tmp_path / "state.json"
    sf.write_text('{"sessions": {}}')
    state = NovaState(sf)
    state.register_session("s1", repos=["r"], transcript_path="/t.jsonl")
    state.set_status("s1", "rotated")
    assert state.sessions["s1"]["status"] == "rotated"


def test_find_sessions_by_chain(tmp_path):
    sf = tmp_path / "state.json"
    sf.write_text('{"sessions": {}}')
    state = NovaState(sf)
    state.register_session("s1", repos=["r"], transcript_path="/t1.jsonl", chain_id="c1")
    state.register_session("s2", repos=["r"], transcript_path="/t2.jsonl", chain_id="c1", chain_sequence=2)
    state.register_session("s3", repos=["r"], transcript_path="/t3.jsonl", chain_id="c2")
    result = state.find_sessions_by_chain("c1")
    assert len(result) == 2
    assert "s1" in [r[0] for r in result]
    assert "s2" in [r[0] for r in result]
