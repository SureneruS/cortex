import json

from nova.hooks.session_start import handle_session_start


def test_injects_knowledge_summaries(tmp_path):
    knowledge_dir = tmp_path / "knowledge"
    repo_dir = knowledge_dir / "repo-recruitment-backend"
    global_dir = knowledge_dir / "global"
    repo_dir.mkdir(parents=True)
    global_dir.mkdir(parents=True)

    (repo_dir / "alembic.md").write_text(
        "---\ntitle: Alembic gotchas\nsummary: Use create_type=False for enums\n---\nDetails.\n"
    )
    (global_dir / "pr-workflow.md").write_text(
        "---\ntitle: PR workflow\nsummary: Always check CI before merging\n---\nDetails.\n"
    )

    state_file = tmp_path / "state.json"
    state_file.write_text('{"last_dream_run": null, "sessions": {}}')

    hook_input = {
        "session_id": "abc123",
        "transcript_path": "/path/to/transcript.jsonl",
        "cwd": "/Users/suren/workspace/cercli/recruitment-backend",
    }

    output = handle_session_start(
        hook_input, knowledge_dir=knowledge_dir, state_file=state_file
    )

    assert "additionalContext" in output
    ctx = output["additionalContext"]
    assert "Alembic gotchas" in ctx
    assert "create_type=False" in ctx
    assert "PR workflow" in ctx

    state = json.loads(state_file.read_text())
    assert "abc123" in state["sessions"]
    assert state["sessions"]["abc123"]["repos"] == ["recruitment-backend"]


def test_no_knowledge_returns_empty(tmp_path):
    knowledge_dir = tmp_path / "knowledge"
    knowledge_dir.mkdir()
    state_file = tmp_path / "state.json"
    state_file.write_text('{"last_dream_run": null, "sessions": {}}')

    hook_input = {
        "session_id": "abc123",
        "transcript_path": "/path",
        "cwd": "/Users/suren/workspace/cercli/some-new-repo",
    }

    output = handle_session_start(
        hook_input, knowledge_dir=knowledge_dir, state_file=state_file
    )
    assert output == {}


def test_registers_session_in_state(tmp_path):
    knowledge_dir = tmp_path / "knowledge"
    knowledge_dir.mkdir()
    state_file = tmp_path / "state.json"
    state_file.write_text('{"last_dream_run": null, "sessions": {}}')

    hook_input = {
        "session_id": "xyz789",
        "transcript_path": "/some/path.jsonl",
        "cwd": "/Users/suren/workspace/cercli/frontend",
    }

    handle_session_start(hook_input, knowledge_dir=knowledge_dir, state_file=state_file)

    state = json.loads(state_file.read_text())
    assert "xyz789" in state["sessions"]
    assert state["sessions"]["xyz789"]["repos"] == ["frontend"]
    assert state["sessions"]["xyz789"]["memory_injected"] is False


def test_malformed_knowledge_file_skipped(tmp_path):
    knowledge_dir = tmp_path / "knowledge"
    global_dir = knowledge_dir / "global"
    global_dir.mkdir(parents=True)

    (global_dir / "good.md").write_text(
        "---\ntitle: Good\nsummary: Works fine\n---\nContent.\n"
    )
    (global_dir / "bad.md").write_text("No frontmatter here, just text.")

    state_file = tmp_path / "state.json"
    state_file.write_text('{"last_dream_run": null, "sessions": {}}')

    hook_input = {"session_id": "s1", "transcript_path": "/p", "cwd": "/some/repo"}

    output = handle_session_start(
        hook_input, knowledge_dir=knowledge_dir, state_file=state_file
    )
    assert "Good" in output.get("additionalContext", "")


def test_registers_tmux_target_from_env(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_SESSION_NAME", "recruitment-backend")
    state_file = tmp_path / "state.json"
    state_file.write_text('{"last_dream_run": null, "sessions": {}, "slack": {}}')

    hook_input = {
        "session_id": "sess1",
        "transcript_path": "/tmp/t.jsonl",
        "cwd": "/path/to/recruitment-backend",
    }
    handle_session_start(hook_input, knowledge_dir=tmp_path / "k", state_file=state_file)

    data = json.loads(state_file.read_text())
    assert data["sessions"]["sess1"]["tmux_target"] == "sessions:recruitment-backend"
    assert data["sessions"]["sess1"]["tmux_window"] == "recruitment-backend"


def test_no_tmux_when_env_not_set(tmp_path, monkeypatch):
    monkeypatch.delenv("NOVA_SESSION_NAME", raising=False)
    state_file = tmp_path / "state.json"
    state_file.write_text('{"last_dream_run": null, "sessions": {}, "slack": {}}')

    hook_input = {
        "session_id": "sess1",
        "transcript_path": "/tmp/t.jsonl",
        "cwd": "/path/to/recruitment-backend",
    }
    handle_session_start(hook_input, knowledge_dir=tmp_path / "k", state_file=state_file)

    data = json.loads(state_file.read_text())
    assert data["sessions"]["sess1"].get("tmux_target") is None
