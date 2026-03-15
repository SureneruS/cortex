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


def test_writes_injection_manifest(tmp_path):
    knowledge_dir = tmp_path / "knowledge"
    repo_dir = knowledge_dir / "repo-recruitment-backend"
    repo_dir.mkdir(parents=True)

    (repo_dir / "lazy-raise.md").write_text(
        "---\ntitle: SQLAlchemy lazy='raise' testing pattern\nsummary: Use lazy raise\n---\nContent.\n"
    )

    state_file = tmp_path / "state.json"
    state_file.write_text('{"last_dream_run": null, "sessions": {}}')
    sessions_dir = tmp_path / "sessions"

    hook_input = {
        "session_id": "abc123",
        "transcript_path": "/path/to/transcript.jsonl",
        "cwd": "/Users/suren/workspace/cercli/recruitment-backend",
    }

    handle_session_start(
        hook_input,
        knowledge_dir=knowledge_dir,
        state_file=state_file,
        sessions_dir=sessions_dir,
    )

    manifest_path = sessions_dir / "abc123" / "injected.json"
    assert manifest_path.exists()

    manifest = json.loads(manifest_path.read_text())
    assert manifest["session_id"] == "abc123"
    assert "timestamp" in manifest
    assert manifest["repo"] == "recruitment-backend"
    assert len(manifest["entries"]) == 1
    assert manifest["entries"][0]["file"] == "repo-recruitment-backend/lazy-raise.md"
    assert manifest["entries"][0]["title"] == "SQLAlchemy lazy='raise' testing pattern"


def test_no_manifest_when_no_entries(tmp_path):
    knowledge_dir = tmp_path / "knowledge"
    knowledge_dir.mkdir()

    state_file = tmp_path / "state.json"
    state_file.write_text('{"last_dream_run": null, "sessions": {}}')
    sessions_dir = tmp_path / "sessions"

    hook_input = {
        "session_id": "abc123",
        "transcript_path": "/path",
        "cwd": "/Users/suren/workspace/cercli/some-repo",
    }

    handle_session_start(
        hook_input,
        knowledge_dir=knowledge_dir,
        state_file=state_file,
        sessions_dir=sessions_dir,
    )

    assert not (sessions_dir / "abc123").exists()


def test_env_file_injection(tmp_path, monkeypatch):
    knowledge_dir = tmp_path / "knowledge"
    repo_dir = knowledge_dir / "repo-myrepo"
    repo_dir.mkdir(parents=True)

    (repo_dir / "pattern.md").write_text(
        "---\ntitle: A pattern\nsummary: Some summary\n---\nContent.\n"
    )

    state_file = tmp_path / "state.json"
    state_file.write_text('{"last_dream_run": null, "sessions": {}}')
    sessions_dir = tmp_path / "sessions"

    env_file = tmp_path / "claude_env"
    env_file.write_text("")
    monkeypatch.setenv("CLAUDE_ENV_FILE", str(env_file))

    hook_input = {
        "session_id": "sess42",
        "transcript_path": "/path",
        "cwd": "/path/to/myrepo",
    }

    handle_session_start(
        hook_input,
        knowledge_dir=knowledge_dir,
        state_file=state_file,
        sessions_dir=sessions_dir,
    )

    content = env_file.read_text()
    assert 'export CLAUDE_CODE_SESSION_ID="sess42"' in content


def test_no_env_file_no_error(tmp_path, monkeypatch):
    monkeypatch.delenv("CLAUDE_ENV_FILE", raising=False)

    knowledge_dir = tmp_path / "knowledge"
    repo_dir = knowledge_dir / "repo-myrepo"
    repo_dir.mkdir(parents=True)

    (repo_dir / "pattern.md").write_text(
        "---\ntitle: A pattern\nsummary: Some summary\n---\nContent.\n"
    )

    state_file = tmp_path / "state.json"
    state_file.write_text('{"last_dream_run": null, "sessions": {}}')
    sessions_dir = tmp_path / "sessions"

    hook_input = {
        "session_id": "sess99",
        "transcript_path": "/path",
        "cwd": "/path/to/myrepo",
    }

    handle_session_start(
        hook_input,
        knowledge_dir=knowledge_dir,
        state_file=state_file,
        sessions_dir=sessions_dir,
    )
