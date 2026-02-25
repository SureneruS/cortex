import json
from pathlib import Path

from nova.hooks.pre_compact import handle_pre_compact


def _make_session_state(transcript_path="/t.jsonl", repos=None):
    return {
        "repos": repos or ["my-repo"],
        "transcript_path": transcript_path,
        "memory_injected": True,
        "goal": "fix bugs",
        "started_at": "2026-01-01T00:00:00Z",
        "last_active_at": "2026-01-01T01:00:00Z",
        "tmux_target": None,
        "tmux_window": None,
        "slack_thread_ts": None,
        "slack_channel": None,
        "chain_id": None,
        "chain_sequence": 1,
        "parent_session_id": None,
        "compaction_count": 0,
        "status": "active",
    }


def test_captures_transcript_on_compact(tmp_path):
    state_file = tmp_path / "state.json"
    captures_dir = tmp_path / "captures"
    captures_dir.mkdir()

    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        json.dumps({"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "I fixed the bug by changing X to Y."}]}}) + "\n"
        + json.dumps({"type": "user", "message": {"role": "user", "content": "great, what else?"}}) + "\n"
        + json.dumps({"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "Now let me refactor the tests."}]}}) + "\n"
    )

    state_file.write_text(json.dumps({
        "sessions": {
            "abc123": _make_session_state(str(transcript)),
        }
    }))

    hook_input = {
        "session_id": "abc123",
        "transcript_path": str(transcript),
    }

    result = handle_pre_compact(hook_input, state_file=state_file, captures_dir=captures_dir)
    assert result == {}

    capture_files = list(captures_dir.glob("*.md"))
    assert len(capture_files) == 1

    content = capture_files[0].read_text()
    assert "abc123" in content
    assert "my-repo" in content
    assert "I fixed the bug" in content

    state = json.loads(state_file.read_text())
    assert state["sessions"]["abc123"]["compaction_count"] == 1


def test_skips_non_nova_session(tmp_path):
    state_file = tmp_path / "state.json"
    captures_dir = tmp_path / "captures"
    captures_dir.mkdir()
    state_file.write_text('{"sessions": {}}')

    hook_input = {
        "session_id": "unknown-session",
        "transcript_path": "/nonexistent",
    }

    result = handle_pre_compact(hook_input, state_file=state_file, captures_dir=captures_dir)
    assert result == {}
    assert len(list(captures_dir.glob("*.md"))) == 0


def test_skips_missing_state_file(tmp_path):
    captures_dir = tmp_path / "captures"
    captures_dir.mkdir()

    hook_input = {
        "session_id": "abc",
        "transcript_path": "/nonexistent",
    }

    result = handle_pre_compact(
        hook_input,
        state_file=tmp_path / "no-state.json",
        captures_dir=captures_dir,
    )
    assert result == {}
