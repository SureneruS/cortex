import json
from unittest.mock import MagicMock, patch

from nova.rotation import RotationManager


def _make_state_file(tmp_path, sessions=None):
    sf = tmp_path / "state.json"
    sf.write_text(json.dumps({"sessions": sessions or {}}))
    return sf


def _make_session(
    tmux_window="test-session",
    transcript_path="/tmp/t.jsonl",
    chain_id="chain-1",
    chain_sequence=1,
    **overrides,
):
    base = {
        "repos": ["my-repo"],
        "transcript_path": transcript_path,
        "memory_injected": True,
        "goal": "do stuff",
        "started_at": "2026-01-01T00:00:00Z",
        "last_active_at": "2026-01-01T01:00:00Z",
        "tmux_target": f"sessions:{tmux_window}",
        "tmux_window": tmux_window,
        "slack_thread_ts": "1234.5678",
        "slack_channel": "C123",
        "chain_id": chain_id,
        "chain_sequence": chain_sequence,
        "parent_session_id": None,
        "compaction_count": 0,
        "status": "active",
    }
    base.update(overrides)
    return base


@patch("nova.rotation.send_keys")
@patch("nova.rotation.has_window", return_value=True)
def test_send_command_and_wait_success(mock_has_window, mock_send_keys, tmp_path):
    transcript = tmp_path / "t.jsonl"
    transcript.write_text("")

    sf = _make_state_file(tmp_path, {"s1": _make_session(transcript_path=str(transcript))})
    mgr = RotationManager(state_file=sf, poster=MagicMock(), config={"memorize_timeout_seconds": 1})

    def grow_transcript(*args, **kwargs):
        transcript.write_text(
            json.dumps({"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "Done."}]}}) + "\n"
        )

    mock_send_keys.side_effect = grow_transcript

    result = mgr._send_command_and_wait("sessions:test-session", "/memorize", str(transcript), timeout=2)
    assert result is True
    mock_send_keys.assert_called_once_with("sessions:test-session", "/memorize")


@patch("nova.rotation.send_keys")
def test_send_command_timeout(mock_send_keys, tmp_path):
    transcript = tmp_path / "t.jsonl"
    transcript.write_text("")

    sf = _make_state_file(tmp_path, {"s1": _make_session(transcript_path=str(transcript))})
    mgr = RotationManager(state_file=sf, poster=MagicMock(), config={"memorize_timeout_seconds": 1})

    result = mgr._send_command_and_wait("sessions:test-session", "/memorize", str(transcript), timeout=1)
    assert result is False


def test_extract_last_assistant_text(tmp_path):
    transcript = tmp_path / "t.jsonl"
    entries = [
        json.dumps({"type": "user", "message": {"role": "user", "content": "/handoff"}}),
        json.dumps({"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "## Goal\nFix the auth bug\n## Progress\n- Found root cause"}]}}),
    ]
    transcript.write_text("\n".join(entries) + "\n")

    sf = _make_state_file(tmp_path, {"s1": _make_session()})
    mgr = RotationManager(state_file=sf, poster=MagicMock(), config={})

    handoff = mgr._extract_last_assistant_text(str(transcript))
    assert "Fix the auth bug" in handoff
    assert "Found root cause" in handoff


def test_extract_last_assistant_text_missing_file(tmp_path):
    sf = _make_state_file(tmp_path, {})
    mgr = RotationManager(state_file=sf, poster=MagicMock(), config={})
    assert mgr._extract_last_assistant_text("/nonexistent.jsonl") == ""


@patch("nova.rotation.is_client_attached", return_value=False)
def test_check_and_rotate_posts_warning(mock_attached, tmp_path):
    sf = _make_state_file(tmp_path, {"s1": _make_session()})
    poster = MagicMock()
    mgr = RotationManager(
        state_file=sf,
        poster=poster,
        config={"idle_threshold_minutes": 1, "warning_delay_seconds": 60},
    )

    mgr.check_and_rotate({"s1": 120})
    poster.post_reply.assert_called_once()
    call_kwargs = poster.post_reply.call_args[1]
    assert "HOLD" in call_kwargs["text"]
    assert "s1" in mgr._pending


def test_cancel_rotation(tmp_path):
    sf = _make_state_file(tmp_path, {})
    mgr = RotationManager(state_file=sf, poster=MagicMock(), config={})
    mgr._pending["s1"] = 9999999999
    mgr.cancel_rotation("s1")
    assert "s1" not in mgr._pending


@patch("nova.rotation.is_client_attached", return_value=True)
def test_check_and_rotate_skips_attached_session(mock_attached, tmp_path):
    sf = _make_state_file(tmp_path, {"s1": _make_session()})
    poster = MagicMock()
    mgr = RotationManager(state_file=sf, poster=poster, config={"idle_threshold_minutes": 1})

    mgr.check_and_rotate({"s1": 120})
    poster.post_reply.assert_not_called()


@patch("nova.rotation.is_client_attached", return_value=False)
def test_check_and_rotate_skips_no_slack_thread(mock_attached, tmp_path):
    session = _make_session(slack_thread_ts=None)
    sf = _make_state_file(tmp_path, {"s1": session})
    poster = MagicMock()
    mgr = RotationManager(state_file=sf, poster=poster, config={"idle_threshold_minutes": 1})

    mgr.check_and_rotate({"s1": 120})
    poster.post_reply.assert_not_called()
