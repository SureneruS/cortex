import json
from pathlib import Path

import pytest

from nova.cli.transcripts import (
    extract_compact_summaries,
    extract_post_compact_messages,
)


def _write_transcript(path: Path, records: list[dict]):
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n")


def test_extract_compact_summary(tmp_path):
    transcript = tmp_path / "session.jsonl"
    records = [
        {"type": "user", "message": {"content": "Fix the bug"}},
        {
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": "Working on it."}]},
        },
        {
            "type": "system",
            "subtype": "compact_boundary",
            "compactMetadata": {"trigger": "auto", "preTokens": 150000},
            "timestamp": "2026-02-22T10:00:00Z",
        },
        {
            "type": "user",
            "message": {
                "content": "This session is being continued from a previous conversation that ran out of context. The summary below covers the earlier portion.\n\nWorked on OAuth bug. Key finding: token locking needed."
            },
        },
        {"type": "user", "message": {"content": "Now continue with the next task"}},
    ]
    _write_transcript(transcript, records)
    summaries = extract_compact_summaries(transcript)
    assert len(summaries) == 1
    assert "OAuth" in summaries[0]["content"]
    assert summaries[0]["trigger"] == "auto"
    assert summaries[0]["pre_tokens"] == 150000


def test_no_compact_summary(tmp_path):
    transcript = tmp_path / "session.jsonl"
    records = [
        {"type": "user", "message": {"content": "Hello"}},
        {
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": "Hi!"}]},
        },
    ]
    _write_transcript(transcript, records)
    summaries = extract_compact_summaries(transcript)
    assert len(summaries) == 0


def test_extract_post_compact_messages(tmp_path):
    transcript = tmp_path / "session.jsonl"
    records = [
        {"type": "user", "message": {"content": "old message"}},
        {
            "type": "system",
            "subtype": "compact_boundary",
            "compactMetadata": {"trigger": "auto", "preTokens": 100000},
        },
        {
            "type": "user",
            "message": {"content": "This session is being continued...summary here"},
        },
        {"type": "user", "message": {"content": "Do the new thing"}},
        {
            "type": "assistant",
            "message": {
                "content": [{"type": "text", "text": "Working on the new thing."}]
            },
        },
    ]
    _write_transcript(transcript, records)
    messages = extract_post_compact_messages(transcript)
    assert len(messages) >= 2
    assert any("new thing" in m["content"] for m in messages)
    assert not any("old message" in m["content"] for m in messages)


def test_multiple_compacts(tmp_path):
    transcript = tmp_path / "session.jsonl"
    records = [
        {"type": "user", "message": {"content": "first era"}},
        {
            "type": "system",
            "subtype": "compact_boundary",
            "compactMetadata": {"trigger": "auto", "preTokens": 100000},
        },
        {
            "type": "user",
            "message": {"content": "This session is being continued...first summary"},
        },
        {"type": "user", "message": {"content": "second era work"}},
        {
            "type": "system",
            "subtype": "compact_boundary",
            "compactMetadata": {"trigger": "manual", "preTokens": 170000},
        },
        {
            "type": "user",
            "message": {"content": "This session is being continued...second summary"},
        },
        {"type": "user", "message": {"content": "third era work"}},
    ]
    _write_transcript(transcript, records)
    summaries = extract_compact_summaries(transcript)
    assert len(summaries) == 2
    assert "first summary" in summaries[0]["content"]
    assert "second summary" in summaries[1]["content"]
    messages = extract_post_compact_messages(transcript)
    assert any("third era" in m["content"] for m in messages)
    assert not any("second era" in m["content"] for m in messages)


def test_file_history_snapshots_skipped(tmp_path):
    """file-history-snapshot records between boundary and summary should be skipped."""
    transcript = tmp_path / "session.jsonl"
    records = [
        {"type": "user", "message": {"content": "work"}},
        {
            "type": "system",
            "subtype": "compact_boundary",
            "compactMetadata": {"trigger": "auto", "preTokens": 100000},
        },
        {"type": "file-history-snapshot", "files": {"foo.py": "abc"}},
        {"type": "file-history-snapshot", "files": {"bar.py": "def"}},
        {
            "type": "user",
            "message": {"content": "This session is being continued...the summary"},
        },
        {"type": "user", "message": {"content": "new work after compact"}},
    ]
    _write_transcript(transcript, records)
    summaries = extract_compact_summaries(transcript)
    assert len(summaries) == 1
    assert "the summary" in summaries[0]["content"]


def test_malformed_json_lines_skipped(tmp_path):
    """Malformed JSON lines should be skipped gracefully."""
    transcript = tmp_path / "session.jsonl"
    content = '{"type": "user", "message": {"content": "hello"}}\nNOT_JSON\n{"type": "assistant", "message": {"content": [{"type": "text", "text": "hi"}]}}\n'
    transcript.write_text(content)
    summaries = extract_compact_summaries(transcript)
    assert summaries == []


def test_real_transcript():
    """Test against an actual Claude Code transcript if available."""
    real_path = (
        Path.home()
        / ".claude/projects/-Users-suren-workspace-cercli/8472b362-015a-4015-99e0-6de083c93004.jsonl"
    )
    if not real_path.exists():
        pytest.skip("Real transcript not available")
    summaries = extract_compact_summaries(real_path)
    assert len(summaries) >= 1
    assert any(
        "Nova" in s["content"] or "session" in s["content"].lower() for s in summaries
    )
