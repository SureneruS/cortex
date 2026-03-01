import json

from nova.hooks.pre_compact import handle_pre_compact


def _make_transcript_line(role, text, timestamp="2026-03-01T10:00:00Z"):
    if role == "assistant":
        content = [{"type": "text", "text": text}]
    else:
        content = text
    return json.dumps({
        "type": role,
        "timestamp": timestamp,
        "message": {"role": role, "content": content},
    })


def _make_session_state(transcript_path="/t.jsonl", repos=None, compact_cursor=None):
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
        "compact_cursor": compact_cursor or {"line": 0, "byte": 0, "time": ""},
        "status": "active",
    }


def test_writes_queue_job_on_compact(tmp_path):
    state_file = tmp_path / "state.json"
    queue_dir = tmp_path / "queue"

    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        _make_transcript_line("assistant", "I fixed the bug.", "2026-03-01T10:00:00Z") + "\n"
        + _make_transcript_line("user", "great, what else?", "2026-03-01T10:05:00Z") + "\n"
        + _make_transcript_line("assistant", "Now let me refactor.", "2026-03-01T10:10:00Z") + "\n"
    )

    state_file.write_text(json.dumps({
        "sessions": {
            "abc12345-6789": _make_session_state(str(transcript)),
        }
    }))

    hook_input = {
        "session_id": "abc12345-6789",
        "transcript_path": str(transcript),
    }

    result = handle_pre_compact(hook_input, state_file=state_file, queue_dir=queue_dir)
    assert result == {}

    job_files = list(queue_dir.glob("*.json"))
    assert len(job_files) == 1

    job = json.loads(job_files[0].read_text())
    assert job["session_id"] == "abc12345-6789"
    assert job["from_line"] == 0
    assert job["to_line"] == 3
    assert job["from_byte"] == 0
    assert job["to_byte"] > 0
    assert job["from_time"] == "2026-03-01T10:00:00Z"
    assert job["to_time"] == "2026-03-01T10:10:00Z"
    assert job["repos"] == ["my-repo"]

    state = json.loads(state_file.read_text())
    assert state["sessions"]["abc12345-6789"]["compaction_count"] == 1
    assert state["sessions"]["abc12345-6789"]["compact_cursor"]["line"] == 3


def test_cursor_updated_after_compact(tmp_path):
    state_file = tmp_path / "state.json"
    queue_dir = tmp_path / "queue"

    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        _make_transcript_line("user", "hello", "2026-03-01T10:00:00Z") + "\n"
        + _make_transcript_line("assistant", "hi", "2026-03-01T10:01:00Z") + "\n"
    )

    state_file.write_text(json.dumps({
        "sessions": {
            "sess1": _make_session_state(str(transcript)),
        }
    }))

    handle_pre_compact(
        {"session_id": "sess1", "transcript_path": str(transcript)},
        state_file=state_file,
        queue_dir=queue_dir,
    )

    state = json.loads(state_file.read_text())
    cursor = state["sessions"]["sess1"]["compact_cursor"]
    assert cursor["line"] == 2
    assert cursor["byte"] > 0
    assert cursor["time"] == "2026-03-01T10:01:00Z"


def test_second_compaction_starts_from_cursor(tmp_path):
    state_file = tmp_path / "state.json"
    queue_dir = tmp_path / "queue"

    lines = [
        _make_transcript_line("user", "first section", "2026-03-01T10:00:00Z"),
        _make_transcript_line("assistant", "response 1", "2026-03-01T10:01:00Z"),
        _make_transcript_line("user", "second section", "2026-03-01T11:00:00Z"),
        _make_transcript_line("assistant", "response 2", "2026-03-01T11:01:00Z"),
    ]
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text("\n".join(lines) + "\n")

    state_file.write_text(json.dumps({
        "sessions": {
            "sess1": _make_session_state(str(transcript)),
        }
    }))

    # First compaction
    handle_pre_compact(
        {"session_id": "sess1", "transcript_path": str(transcript)},
        state_file=state_file,
        queue_dir=queue_dir,
    )

    # Append more content to transcript
    with transcript.open("a") as f:
        f.write(_make_transcript_line("user", "third section", "2026-03-01T12:00:00Z") + "\n")
        f.write(_make_transcript_line("assistant", "response 3", "2026-03-01T12:01:00Z") + "\n")

    # Second compaction
    handle_pre_compact(
        {"session_id": "sess1", "transcript_path": str(transcript)},
        state_file=state_file,
        queue_dir=queue_dir,
    )

    job_files = sorted(queue_dir.glob("*.json"))
    assert len(job_files) == 2

    job2 = json.loads(job_files[1].read_text())
    assert job2["from_line"] == 4
    assert job2["to_line"] == 6
    assert job2["from_time"] == "2026-03-01T11:01:00Z"  # carried from previous cursor
    assert job2["to_time"] == "2026-03-01T12:01:00Z"

    state = json.loads(state_file.read_text())
    assert state["sessions"]["sess1"]["compaction_count"] == 2


def test_no_job_for_empty_section(tmp_path):
    state_file = tmp_path / "state.json"
    queue_dir = tmp_path / "queue"

    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        _make_transcript_line("user", "hello", "2026-03-01T10:00:00Z") + "\n"
    )

    # Cursor already at line 1 (past the only line)
    state_file.write_text(json.dumps({
        "sessions": {
            "sess1": _make_session_state(
                str(transcript),
                compact_cursor={"line": 1, "byte": 200, "time": "2026-03-01T10:00:00Z"},
            ),
        }
    }))

    handle_pre_compact(
        {"session_id": "sess1", "transcript_path": str(transcript)},
        state_file=state_file,
        queue_dir=queue_dir,
    )

    # No queue job written, but compaction count still incremented
    assert not queue_dir.exists() or len(list(queue_dir.glob("*.json"))) == 0
    state = json.loads(state_file.read_text())
    assert state["sessions"]["sess1"]["compaction_count"] == 1


def test_skips_non_nova_session(tmp_path):
    state_file = tmp_path / "state.json"
    queue_dir = tmp_path / "queue"
    state_file.write_text('{"sessions": {}}')

    result = handle_pre_compact(
        {"session_id": "unknown-session", "transcript_path": "/nonexistent"},
        state_file=state_file,
        queue_dir=queue_dir,
    )
    assert result == {}
    assert not queue_dir.exists()


def test_skips_missing_state_file(tmp_path):
    result = handle_pre_compact(
        {"session_id": "abc", "transcript_path": "/nonexistent"},
        state_file=tmp_path / "no-state.json",
        queue_dir=tmp_path / "queue",
    )
    assert result == {}
