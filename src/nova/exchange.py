from __future__ import annotations

import json
import logging
import sys
import traceback
from pathlib import Path

from nova.config import load_config
from nova.lib.state import NovaState
from nova.slack import SlackPoster
from nova.tmux import has_window, send_keys, send_raw_key, send_option_select, TMUX_SESSION

logger = logging.getLogger(__name__)

MAX_SLACK_TEXT = 3000


def _log(msg: str) -> None:
    print(msg, flush=True)

NOVA_DIR = Path.home() / ".nova"


class TranscriptWatcher:
    def __init__(
        self,
        state_file: Path,
        poster: SlackPoster,
        prompt_tracker: PromptStateTracker | None = None,
    ):
        self._state_file = state_file
        self._poster = poster
        self._prompt_tracker = prompt_tracker or PromptStateTracker()
        self._offsets: dict[str, int] = {}

    def poll(self):
        if not self._state_file.exists():
            return

        try:
            state = NovaState(self._state_file)
        except Exception:
            return

        for sid, session in state.sessions.items():
            thread_ts = session.get("slack_thread_ts")
            channel = session.get("slack_channel")
            transcript_path = session.get("transcript_path")

            if not thread_ts or not channel or not transcript_path:
                continue

            path = Path(transcript_path)
            if not path.exists():
                continue

            current_size = path.stat().st_size

            if sid not in self._offsets:
                self._offsets[sid] = current_size
                continue

            if current_size <= self._offsets[sid]:
                continue

            try:
                with open(path) as f:
                    f.seek(self._offsets[sid])
                    new_content = f.read()
            except Exception:
                continue

            self._offsets[sid] = current_size
            self._process_new_content(new_content, channel, thread_ts)

    def _process_new_content(self, content: str, channel: str, thread_ts: str):
        for line in content.strip().split("\n"):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            msg = entry.get("message", {})
            if msg.get("role") != "assistant":
                continue

            content_items = msg.get("content", [])

            question = self._extract_ask_question(content_items)
            if question:
                self._handle_question(question, channel, thread_ts)
                continue

            if self._has_permission_tool_use(content_items):
                self._prompt_tracker.set_permission(thread_ts, "permission requested")
                continue

            text = self._extract_text(content_items)
            if not text:
                continue

            self._prompt_tracker.clear(thread_ts)

            if len(text) > MAX_SLACK_TEXT:
                text = text[:MAX_SLACK_TEXT] + "...(truncated)"

            try:
                self._poster.post_reply(
                    channel=channel, thread_ts=thread_ts, text=text
                )
                _log(f"[watcher] Posted assistant response ({len(text)} chars)")
            except Exception:
                _log(f"[watcher] ERROR posting response:\n{traceback.format_exc()}")

    def _handle_question(self, question: dict, channel: str, thread_ts: str):
        options = question.get("options", [])
        self._prompt_tracker.set_question(thread_ts, options)

        lines = [f"*{question.get('question', 'Choose an option')}*", ""]
        for i, opt in enumerate(options, 1):
            label = opt.get("label", "")
            desc = opt.get("description", "")
            lines.append(f"*{i}.* {label}" + (f" — {desc}" if desc else ""))
        lines.append(f"*{len(options) + 1}.* Other (type your answer)")
        lines.append("\n_Reply with a number to select_")

        try:
            self._poster.post_reply(
                channel=channel, thread_ts=thread_ts, text="\n".join(lines)
            )
            _log(f"[watcher] Posted question with {len(options)} options")
        except Exception:
            _log(f"[watcher] ERROR posting question:\n{traceback.format_exc()}")

    @staticmethod
    def _extract_ask_question(content: list) -> dict | None:
        for item in content:
            if not isinstance(item, dict) or item.get("type") != "tool_use":
                continue
            if item.get("name") != "AskUserQuestion":
                continue
            questions = item.get("input", {}).get("questions", [])
            if questions:
                return questions[0]
        return None

    @staticmethod
    def _has_permission_tool_use(content: list) -> bool:
        for item in content:
            if not isinstance(item, dict) or item.get("type") != "tool_use":
                continue
            name = item.get("name", "")
            if name in ("Bash", "Write", "Edit"):
                return True
        return False

    @staticmethod
    def _extract_text(content: list) -> str:
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(item["text"])
        return "\n".join(parts)


class IdleTracker:
    def __init__(self):
        self._last_sizes: dict[str, int] = {}
        self._idle_since: dict[str, float] = {}

    def update(self, session_id: str, current_size: int):
        import time as _time

        prev_size = self._last_sizes.get(session_id)
        self._last_sizes[session_id] = current_size

        if prev_size is None:
            self._idle_since[session_id] = _time.time()
            return

        if current_size != prev_size:
            self._idle_since[session_id] = _time.time()
        elif session_id not in self._idle_since:
            self._idle_since[session_id] = _time.time()

    def get_idle_seconds(self) -> dict[str, float]:
        import time as _time

        now = _time.time()
        return {sid: now - since for sid, since in self._idle_since.items()}

    def remove(self, session_id: str):
        self._last_sizes.pop(session_id, None)
        self._idle_since.pop(session_id, None)


class PromptStateTracker:
    def __init__(self):
        self._states: dict[str, dict] = {}

    def set_question(self, thread_ts: str, options: list[dict]):
        self._states[thread_ts] = {
            "type": "question",
            "options": options,
            "option_count": len(options),
        }

    def set_permission(self, thread_ts: str, message: str):
        self._states[thread_ts] = {"type": "permission", "message": message}

    def clear(self, thread_ts: str):
        self._states.pop(thread_ts, None)

    def get(self, thread_ts: str) -> dict | None:
        return self._states.get(thread_ts)


class ExchangeHandler:
    def __init__(
        self,
        state_file: Path | None = None,
        config_path: Path | None = None,
        prompt_tracker: PromptStateTracker | None = None,
        rotation_manager: object | None = None,
    ):
        self._state_file = state_file or (NOVA_DIR / "state.json")
        self._poster: SlackPoster | None = None
        self._prompt_tracker = prompt_tracker or PromptStateTracker()
        self._rotation_manager = rotation_manager

        try:
            config = load_config(config_path)
            slack_config = config["slack"]
            self._poster = SlackPoster(
                bot_token=slack_config["bot_token"],
                target_user_id=slack_config.get("target_user_id", ""),
            )
        except Exception:
            pass

        self._bot_user_id: str | None = None
        if self._state_file.exists():
            try:
                state = NovaState(self._state_file)
                self._bot_user_id = state.slack_config.get("bot_user_id")
            except Exception:
                pass

    def handle_message(
        self,
        channel: str,
        thread_ts: str,
        message_ts: str,
        text: str,
        user: str,
    ) -> bool:
        if self._bot_user_id and user == self._bot_user_id:
            return False

        if not self._state_file.exists():
            return False

        state = NovaState(self._state_file)
        match = state.find_session_by_thread(thread_ts)
        if not match:
            return False

        session_id, session = match

        if text.strip().upper() == "HOLD" and self._rotation_manager:
            self._rotation_manager.cancel_rotation(session_id)
            if self._poster:
                self._poster.post_reply(
                    channel=channel, thread_ts=thread_ts, text="Rotation cancelled."
                )
            return True

        tmux_target = session.get("tmux_target")
        tmux_window = session.get("tmux_window")

        if not tmux_target or not tmux_window:
            return False

        if not has_window(TMUX_SESSION, tmux_window):
            if self._poster:
                self._poster.post_reply(
                    channel=channel,
                    thread_ts=thread_ts,
                    text=f"Session `{tmux_window}` is no longer active.",
                )
            return False

        prompt_state = self._prompt_tracker.get(thread_ts)
        self._send_input(tmux_target, text, prompt_state)
        self._prompt_tracker.clear(thread_ts)
        _log(f"[exchange] Routed reply to {tmux_window} (mode={prompt_state['type'] if prompt_state else 'text'}): {text[:80]}")

        return True

    def _send_input(self, target: str, text: str, prompt_state: dict | None):
        if prompt_state and prompt_state["type"] == "question":
            stripped = text.strip()
            if stripped.isdigit():
                idx = int(stripped) - 1
                if 0 <= idx <= prompt_state["option_count"]:
                    send_option_select(target, idx)
                    return
            # "other" or unrecognized → select Other (last), then type
            option_count = prompt_state["option_count"]
            send_option_select(target, option_count)  # Other is after all options
            send_keys(target, text)
            return

        if prompt_state and prompt_state["type"] == "permission":
            stripped = text.strip().lower()
            if stripped in ("y", "yes", "allow"):
                send_raw_key(target, "y")
                return
            if stripped in ("n", "no", "deny"):
                send_raw_key(target, "n")
                return

        send_keys(target, text)

        if self._poster:
            try:
                self._poster.add_reaction(
                    channel=channel,
                    timestamp=message_ts,
                    emoji="white_check_mark",
                )
            except Exception:
                pass

        return True


def _setup_verbose_logging():
    import sys

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
    )

    # Socket Mode internals — connection lifecycle
    logging.getLogger("slack_sdk.socket_mode.builtin.connection").setLevel(logging.DEBUG)
    logging.getLogger("slack_sdk.socket_mode.builtin.internals").setLevel(logging.DEBUG)
    logging.getLogger("slack_sdk.socket_mode.builtin").setLevel(logging.DEBUG)

    # Web API calls
    logging.getLogger("slack_sdk.web.base_client").setLevel(logging.INFO)

    # Websocket frames (very noisy — keep at INFO to see connect/disconnect but not every frame)
    logging.getLogger("websocket").setLevel(logging.INFO)


def run_exchange(state_file: Path | None = None, config_path: Path | None = None):
    from slack_sdk.socket_mode import SocketModeClient
    from slack_sdk.socket_mode.request import SocketModeRequest
    from slack_sdk.socket_mode.response import SocketModeResponse

    _setup_verbose_logging()

    from nova.rotation import RotationManager

    config = load_config(config_path)
    app_token = config["slack"].get("app_token")
    if not app_token:
        raise ValueError(
            "Slack app_token required for exchange. Set NOVA_SLACK_APP_TOKEN."
        )

    sf = state_file or (NOVA_DIR / "state.json")
    rotation_config = config.get("rotation", {})
    prompt_tracker = PromptStateTracker()
    idle_tracker = IdleTracker()

    rotation_mgr = None
    if rotation_config.get("enabled"):
        _log("[exchange] Session rotation enabled")

    handler = ExchangeHandler(
        state_file=state_file,
        config_path=config_path,
        prompt_tracker=prompt_tracker,
    )

    if rotation_config.get("enabled") and handler._poster:
        rotation_mgr = RotationManager(
            state_file=sf,
            poster=handler._poster,
            config=rotation_config,
        )
        handler._rotation_manager = rotation_mgr

    client = SocketModeClient(
        app_token=app_token,
        web_client=handler._poster._client if handler._poster else None,
        auto_reconnect_enabled=True,
        ping_interval=10,
        trace_enabled=True,
    )

    def process(client: SocketModeClient, req: SocketModeRequest):
        try:
            _log(f"[exchange] << Event received: type={req.type} envelope={req.envelope_id[:12]}...")
            client.send_socket_mode_response(
                SocketModeResponse(envelope_id=req.envelope_id)
            )
            _log(f"[exchange] >> Ack sent for {req.envelope_id[:12]}")

            if req.type != "events_api":
                _log(f"[exchange] Skipping non-events_api: {req.type}")
                return

            event = req.payload.get("event", {})
            event_type = event.get("type", "unknown")
            subtype = event.get("subtype")
            thread_ts = event.get("thread_ts")
            text = event.get("text", "")
            user = event.get("user", "")
            channel = event.get("channel", "")
            ts = event.get("ts", "")

            _log(f"[exchange] Event details: type={event_type} subtype={subtype} "
                 f"channel={channel} ts={ts} thread_ts={thread_ts} user={user}")

            if event_type != "message":
                _log(f"[exchange] Skipping: not a message event")
                return
            if subtype:
                _log(f"[exchange] Skipping: message subtype={subtype}")
                return
            if not thread_ts:
                _log(f"[exchange] Skipping: non-threaded message: {text[:50]}")
                return

            _log(f"[exchange] Processing threaded reply from {user}: {text[:80]}")

            routed = handler.handle_message(
                channel=channel,
                thread_ts=thread_ts,
                message_ts=ts,
                text=text,
                user=user,
            )
            _log(f"[exchange] Route result: {'delivered' if routed else 'not matched'}")
        except Exception:
            _log(f"[exchange] ERROR in callback:\n{traceback.format_exc()}")

    client.socket_mode_request_listeners.append(process)

    watcher = None
    if handler._poster:
        watcher = TranscriptWatcher(sf, handler._poster, prompt_tracker=prompt_tracker)
        watcher.poll()  # initialize offsets, skip existing content

    _log("[exchange] Connecting to Slack Socket Mode...")
    client.connect()
    _log("[exchange] Connected. Listening for messages.")
    _log(f"[exchange] Auto-reconnect: {client.auto_reconnect_enabled}")
    _log(f"[exchange] Ping interval: {client.ping_interval}s")
    _log(f"[exchange] Bot user ID filter: {handler._bot_user_id}")
    _log(f"[exchange] Transcript watcher: {'active' if watcher else 'disabled'}")
    _log(f"[exchange] Rotation: {'enabled' if rotation_mgr else 'disabled'}")
    _log("[exchange] Press Ctrl+C to stop.\n")

    import time

    poll_count = 0
    try:
        while True:
            time.sleep(3)
            if watcher:
                try:
                    watcher.poll()
                    for sid, offset in watcher._offsets.items():
                        idle_tracker.update(sid, offset)
                except Exception:
                    _log(f"[watcher] ERROR:\n{traceback.format_exc()}")
            if rotation_mgr:
                try:
                    idle_seconds = idle_tracker.get_idle_seconds()
                    rotation_mgr.check_and_rotate(idle_seconds)
                except Exception:
                    _log(f"[rotation] ERROR:\n{traceback.format_exc()}")
            poll_count += 1
            if poll_count % 20 == 0:  # heartbeat every ~60s
                connected = client.is_connected() if hasattr(client, "is_connected") else "unknown"
                _log(f"[exchange] heartbeat — connected={connected}")
    except KeyboardInterrupt:
        _log("\n[exchange] Shutting down...")
        client.close()
        _log("[exchange] Disconnected.")
