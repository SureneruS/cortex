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


def test_nonexistent_state_file(tmp_path):
    """Loading from nonexistent file should give empty state."""
    state = NovaState(tmp_path / "missing.json")
    assert state.sessions == {}
    assert state.last_dream_run is None
