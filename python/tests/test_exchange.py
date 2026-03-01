import json
from unittest.mock import patch, MagicMock

from nova.exchange import ExchangeHandler, IdleTracker, TranscriptWatcher, PromptStateTracker


def _make_state_file(tmp_path, sessions=None, slack=None):
    state_file = tmp_path / "state.json"
    data = {"last_dream_run": None, "sessions": sessions or {}, "slack": slack or {}}
    state_file.write_text(json.dumps(data))
    return state_file


def _make_session(**overrides):
    base = {
        "repos": ["rb"],
        "transcript_path": "",
        "memory_injected": True,
        "goal": "test",
        "started_at": "",
        "last_active_at": "",
        "tmux_target": "sessions:rb",
        "tmux_window": "rb",
        "slack_thread_ts": "111.222",
        "slack_channel": "D0ABC",
    }
    base.update(overrides)
    return base


def test_routes_reply_to_session(tmp_path):
    state_file = _make_state_file(tmp_path, sessions={"sess1": _make_session()})
    handler = ExchangeHandler(state_file=state_file)

    with (
        patch("nova.exchange.has_window", return_value=True),
        patch("nova.exchange.send_keys") as mock_send,
    ):
        result = handler.handle_message(
            channel="D0ABC",
            thread_ts="111.222",
            message_ts="333.444",
            text="continue with the tests",
            user="U0USER",
        )

    assert result is True
    mock_send.assert_called_once_with("sessions:rb", "continue with the tests")


def test_ignores_non_session_thread(tmp_path):
    state_file = _make_state_file(tmp_path)
    handler = ExchangeHandler(state_file=state_file)
    result = handler.handle_message(
        channel="D0ABC",
        thread_ts="999.999",
        message_ts="444.555",
        text="random",
        user="U0USER",
    )
    assert result is False


def test_replies_if_session_dead(tmp_path):
    state_file = _make_state_file(tmp_path, sessions={"sess1": _make_session()})
    handler = ExchangeHandler(state_file=state_file)
    mock_poster = MagicMock()
    handler._poster = mock_poster

    with patch("nova.exchange.has_window", return_value=False):
        result = handler.handle_message(
            channel="D0ABC",
            thread_ts="111.222",
            message_ts="555.666",
            text="hello",
            user="U0USER",
        )

    assert result is False
    mock_poster.post_reply.assert_called_once()
    assert "no longer active" in mock_poster.post_reply.call_args.kwargs["text"]


def test_ignores_bot_messages(tmp_path):
    state_file = _make_state_file(tmp_path, slack={"bot_user_id": "U0BOT"})
    handler = ExchangeHandler(state_file=state_file)
    result = handler.handle_message(
        channel="D0ABC",
        thread_ts="111.222",
        message_ts="666.777",
        text="I posted this",
        user="U0BOT",
    )
    assert result is False


def _write_transcript_entry(path, entry):
    with open(path, "a") as f:
        f.write(json.dumps(entry) + "\n")


def _assistant_entry(text):
    return {
        "message": {
            "role": "assistant",
            "content": [{"type": "text", "text": text}],
        }
    }


def _user_entry(text):
    return {"type": "user", "message": {"role": "user", "content": text}}


def _tool_use_entry():
    return {
        "message": {
            "role": "assistant",
            "content": [{"type": "tool_use", "id": "t1", "name": "Read", "input": {}}],
        }
    }


def test_watcher_skips_existing_content(tmp_path):
    transcript = tmp_path / "t.jsonl"
    _write_transcript_entry(transcript, _assistant_entry("old message"))

    state_file = _make_state_file(
        tmp_path,
        sessions={"s1": _make_session(transcript_path=str(transcript))},
    )
    poster = MagicMock()
    watcher = TranscriptWatcher(state_file, poster)

    watcher.poll()
    poster.post_reply.assert_not_called()


def test_watcher_posts_new_assistant_message(tmp_path):
    transcript = tmp_path / "t.jsonl"
    _write_transcript_entry(transcript, _user_entry("hello"))

    state_file = _make_state_file(
        tmp_path,
        sessions={"s1": _make_session(transcript_path=str(transcript))},
    )
    poster = MagicMock()
    watcher = TranscriptWatcher(state_file, poster)

    watcher.poll()  # initialize offset

    _write_transcript_entry(transcript, _assistant_entry("Hi there!"))
    watcher.poll()

    poster.post_reply.assert_called_once_with(
        channel="D0ABC", thread_ts="111.222", text="Hi there!"
    )


def test_watcher_ignores_user_messages(tmp_path):
    transcript = tmp_path / "t.jsonl"
    transcript.touch()

    state_file = _make_state_file(
        tmp_path,
        sessions={"s1": _make_session(transcript_path=str(transcript))},
    )
    poster = MagicMock()
    watcher = TranscriptWatcher(state_file, poster)
    watcher.poll()

    _write_transcript_entry(transcript, _user_entry("just a user msg"))
    watcher.poll()

    poster.post_reply.assert_not_called()


def test_watcher_ignores_tool_use_only(tmp_path):
    transcript = tmp_path / "t.jsonl"
    transcript.touch()

    state_file = _make_state_file(
        tmp_path,
        sessions={"s1": _make_session(transcript_path=str(transcript))},
    )
    poster = MagicMock()
    watcher = TranscriptWatcher(state_file, poster)
    watcher.poll()

    _write_transcript_entry(transcript, _tool_use_entry())
    watcher.poll()

    poster.post_reply.assert_not_called()


def test_watcher_skips_sessions_without_slack_thread(tmp_path):
    transcript = tmp_path / "t.jsonl"
    transcript.touch()

    state_file = _make_state_file(
        tmp_path,
        sessions={"s1": _make_session(slack_thread_ts=None, transcript_path=str(transcript))},
    )
    poster = MagicMock()
    watcher = TranscriptWatcher(state_file, poster)
    watcher.poll()

    _write_transcript_entry(transcript, _assistant_entry("should not post"))
    watcher.poll()

    poster.post_reply.assert_not_called()


def test_watcher_truncates_long_messages(tmp_path):
    transcript = tmp_path / "t.jsonl"
    transcript.touch()

    state_file = _make_state_file(
        tmp_path,
        sessions={"s1": _make_session(transcript_path=str(transcript))},
    )
    poster = MagicMock()
    watcher = TranscriptWatcher(state_file, poster)
    watcher.poll()

    long_text = "x" * 5000
    _write_transcript_entry(transcript, _assistant_entry(long_text))
    watcher.poll()

    posted_text = poster.post_reply.call_args.kwargs["text"]
    assert len(posted_text) < 4000
    assert posted_text.endswith("...(truncated)")


def _ask_question_entry(question="Pick one?", options=None):
    if options is None:
        options = [
            {"label": "Option A", "description": "First choice"},
            {"label": "Option B", "description": "Second choice"},
        ]
    return {
        "message": {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "tu1",
                    "name": "AskUserQuestion",
                    "input": {
                        "questions": [{"question": question, "options": options}]
                    },
                }
            ],
        }
    }


def test_watcher_posts_question_options(tmp_path):
    transcript = tmp_path / "t.jsonl"
    transcript.touch()

    state_file = _make_state_file(
        tmp_path,
        sessions={"s1": _make_session(transcript_path=str(transcript))},
    )
    tracker = PromptStateTracker()
    poster = MagicMock()
    watcher = TranscriptWatcher(state_file, poster, prompt_tracker=tracker)
    watcher.poll()

    _write_transcript_entry(transcript, _ask_question_entry())
    watcher.poll()

    poster.post_reply.assert_called_once()
    posted = poster.post_reply.call_args.kwargs["text"]
    assert "Pick one?" in posted
    assert "1." in posted
    assert "Option A" in posted
    assert "2." in posted
    assert "Option B" in posted
    assert "Other" in posted


def test_watcher_sets_question_state(tmp_path):
    transcript = tmp_path / "t.jsonl"
    transcript.touch()

    state_file = _make_state_file(
        tmp_path,
        sessions={"s1": _make_session(transcript_path=str(transcript))},
    )
    tracker = PromptStateTracker()
    poster = MagicMock()
    watcher = TranscriptWatcher(state_file, poster, prompt_tracker=tracker)
    watcher.poll()

    _write_transcript_entry(transcript, _ask_question_entry())
    watcher.poll()

    state = tracker.get("111.222")
    assert state is not None
    assert state["type"] == "question"
    assert state["option_count"] == 2


def test_handler_sends_option_select_in_question_mode(tmp_path):
    state_file = _make_state_file(tmp_path, sessions={"s1": _make_session()})
    tracker = PromptStateTracker()
    tracker.set_question("111.222", [{"label": "A"}, {"label": "B"}, {"label": "C"}])

    handler = ExchangeHandler(state_file=state_file, prompt_tracker=tracker)

    with (
        patch("nova.exchange.has_window", return_value=True),
        patch("nova.exchange.send_option_select") as mock_select,
    ):
        result = handler.handle_message(
            channel="D0ABC",
            thread_ts="111.222",
            message_ts="333.444",
            text="2",
            user="U0USER",
        )

    assert result is True
    mock_select.assert_called_once_with("sessions:rb", 1)  # 0-indexed: option 2 = index 1
    assert tracker.get("111.222") is None  # cleared after use


def test_handler_sends_permission_approve(tmp_path):
    state_file = _make_state_file(tmp_path, sessions={"s1": _make_session()})
    tracker = PromptStateTracker()
    tracker.set_permission("111.222", "Allow Bash?")

    handler = ExchangeHandler(state_file=state_file, prompt_tracker=tracker)

    with (
        patch("nova.exchange.has_window", return_value=True),
        patch("nova.exchange.send_raw_key") as mock_key,
    ):
        result = handler.handle_message(
            channel="D0ABC",
            thread_ts="111.222",
            message_ts="333.444",
            text="y",
            user="U0USER",
        )

    assert result is True
    mock_key.assert_called_once_with("sessions:rb", "y")


def test_handler_falls_back_to_text_without_state(tmp_path):
    state_file = _make_state_file(tmp_path, sessions={"s1": _make_session()})
    tracker = PromptStateTracker()
    handler = ExchangeHandler(state_file=state_file, prompt_tracker=tracker)

    with (
        patch("nova.exchange.has_window", return_value=True),
        patch("nova.exchange.send_keys") as mock_send,
    ):
        result = handler.handle_message(
            channel="D0ABC",
            thread_ts="111.222",
            message_ts="333.444",
            text="just regular text",
            user="U0USER",
        )

    assert result is True
    mock_send.assert_called_once_with("sessions:rb", "just regular text")


# --- IdleTracker tests ---


def test_idle_tracker_detects_idle_session():
    tracker = IdleTracker()
    tracker.update("s1", current_size=1000)
    tracker.update("s1", current_size=1000)

    idle = tracker.get_idle_seconds()
    assert "s1" in idle
    assert idle["s1"] >= 0


def test_idle_tracker_resets_on_growth():
    tracker = IdleTracker()
    tracker.update("s1", current_size=1000)
    tracker.update("s1", current_size=1000)
    tracker.update("s1", current_size=2000)

    idle = tracker.get_idle_seconds()
    assert idle.get("s1", 0) < 1


def test_idle_tracker_remove():
    tracker = IdleTracker()
    tracker.update("s1", current_size=100)
    tracker.remove("s1")
    assert "s1" not in tracker.get_idle_seconds()


# --- HOLD cancellation test ---


def test_handler_cancels_rotation_on_hold(tmp_path):
    state_file = _make_state_file(
        tmp_path,
        sessions={
            "s1": _make_session(
                chain_id=None,
                chain_sequence=1,
                parent_session_id=None,
                compaction_count=0,
                status="active",
            )
        },
    )

    rotation_mgr = MagicMock()
    handler = ExchangeHandler(state_file=state_file, rotation_manager=rotation_mgr)
    handler._poster = MagicMock()

    with patch("nova.exchange.has_window", return_value=True), \
         patch("nova.exchange.send_keys"):
        handler.handle_message("D0ABC", "111.222", "ts1", "HOLD", "U123")

    rotation_mgr.cancel_rotation.assert_called_once_with("s1")
    handler._poster.post_reply.assert_called_once()
    assert "cancelled" in handler._poster.post_reply.call_args[1]["text"].lower()
