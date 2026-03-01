from nova.hooks.user_prompt import handle_user_prompt
from nova.lib.state import NovaState


def _setup_nova_dir(tmp_path):
    knowledge_dir = tmp_path / "memory" / "knowledge" / "repo-recruitment-backend"
    global_dir = tmp_path / "memory" / "knowledge" / "global"
    captures_dir = tmp_path / "memory" / "captures"
    knowledge_dir.mkdir(parents=True)
    global_dir.mkdir(parents=True)
    captures_dir.mkdir(parents=True)

    (knowledge_dir / "oauth.md").write_text(
        "---\ntitle: OAuth token patterns\nsummary: Token refresh needs locking for concurrent requests\ntags: [oauth, tokens, concurrency]\nrepos: [recruitment-backend]\nsources: [cap1.md]\ncreated_at: '2026-02-22T20:00:00Z'\nschema_version: 1\n---\nDetails about OAuth.\n"
    )
    (global_dir / "testing.md").write_text(
        "---\ntitle: Testing patterns\nsummary: Use Factory Boy with relationship objects not FK scalars\ntags: [testing, factory-boy]\nrepos: [recruitment-backend]\nsources: [cap2.md]\ncreated_at: '2026-02-22T20:00:00Z'\nschema_version: 1\n---\nDetails about testing.\n"
    )
    (captures_dir / "2026-02-22-143012-abc12345.md").write_text(
        "---\nsession: abc12345\nrepos: [recruitment-backend]\ntranscript: /path/to/t.jsonl\ncaptured_at: '2026-02-22T14:30:12Z'\nschema_version: 1\n---\nWorked on OAuth token refresh. Found race condition.\n"
    )

    state_file = tmp_path / "state.json"
    state_file.write_text(
        '{"last_dream_run": null, "sessions": {"sess1": {"repos": ["recruitment-backend"], "transcript_path": "/p", "memory_injected": false, "goal": null}}}'
    )

    return state_file


def test_first_prompt_injects_context(tmp_path):
    state_file = _setup_nova_dir(tmp_path)

    hook_input = {
        "session_id": "sess1",
        "prompt": "fix the OAuth token refresh bug",
    }

    output = handle_user_prompt(hook_input, nova_dir=tmp_path, state_file=state_file)

    assert "additionalContext" in output
    ctx = output["additionalContext"]
    assert "OAuth" in ctx
    assert "token" in ctx.lower() or "Token" in ctx

    state = NovaState(state_file)
    assert state.sessions["sess1"]["memory_injected"] is True
    assert "OAuth" in state.sessions["sess1"]["goal"]


def test_second_prompt_noop(tmp_path):
    state_file = _setup_nova_dir(tmp_path)

    hook_input = {
        "session_id": "sess1",
        "prompt": "fix OAuth bug",
    }
    handle_user_prompt(hook_input, nova_dir=tmp_path, state_file=state_file)

    hook_input2 = {
        "session_id": "sess1",
        "prompt": "now fix the database migration",
    }
    output = handle_user_prompt(hook_input2, nova_dir=tmp_path, state_file=state_file)
    assert output == {}


def test_confirmation_phrase_suggests_memorize(tmp_path):
    state_file = _setup_nova_dir(tmp_path)

    # First prompt — normal injection
    handle_user_prompt(
        {"session_id": "sess1", "prompt": "fix OAuth bug"},
        nova_dir=tmp_path,
        state_file=state_file,
    )

    # Second prompt with confirmation phrase
    output = handle_user_prompt(
        {"session_id": "sess1", "prompt": "that worked, the OAuth bug is gone"},
        nova_dir=tmp_path,
        state_file=state_file,
    )
    assert "additionalContext" in output
    assert "/memorize" in output["additionalContext"]


def test_confirmation_phrase_not_on_first_prompt(tmp_path):
    """Confirmation detection should not fire on the first prompt."""
    state_file = _setup_nova_dir(tmp_path)

    output = handle_user_prompt(
        {"session_id": "sess1", "prompt": "that worked, now let's move on"},
        nova_dir=tmp_path,
        state_file=state_file,
    )
    # First prompt should do normal injection, not confirmation detection
    # (no matching knowledge for "that worked" so empty)
    assert "/memorize" not in output.get("additionalContext", "")


def test_unregistered_session_does_not_crash(tmp_path):
    state_file = _setup_nova_dir(tmp_path)

    hook_input = {
        "session_id": "unknown_session",
        "prompt": "fix OAuth",
    }

    output = handle_user_prompt(hook_input, nova_dir=tmp_path, state_file=state_file)
    assert isinstance(output, dict)


def test_no_matching_knowledge(tmp_path):
    state_file = _setup_nova_dir(tmp_path)

    hook_input = {
        "session_id": "sess1",
        "prompt": "set up kubernetes deployment",
    }

    output = handle_user_prompt(hook_input, nova_dir=tmp_path, state_file=state_file)
    assert output == {}

    state = NovaState(state_file)
    assert state.sessions["sess1"]["memory_injected"] is True


def test_empty_prompt_noop(tmp_path):
    state_file = _setup_nova_dir(tmp_path)

    hook_input = {
        "session_id": "sess1",
        "prompt": "",
    }

    output = handle_user_prompt(hook_input, nova_dir=tmp_path, state_file=state_file)
    assert output == {}


def test_captures_scored_by_content_fallback(tmp_path):
    """Captures without title/summary use first line of body content."""
    state_file = _setup_nova_dir(tmp_path)

    hook_input = {
        "session_id": "sess1",
        "prompt": "OAuth token refresh race condition",
    }

    output = handle_user_prompt(hook_input, nova_dir=tmp_path, state_file=state_file)

    assert "additionalContext" in output
    ctx = output["additionalContext"]
    assert "OAuth" in ctx


def test_malformed_file_skipped(tmp_path):
    state_file = _setup_nova_dir(tmp_path)

    bad_file = tmp_path / "memory" / "knowledge" / "global" / "broken.md"
    bad_file.write_text("not valid frontmatter {{{")

    hook_input = {
        "session_id": "sess1",
        "prompt": "fix OAuth token refresh",
    }

    output = handle_user_prompt(hook_input, nova_dir=tmp_path, state_file=state_file)
    assert "additionalContext" in output
    assert "OAuth" in output["additionalContext"]
