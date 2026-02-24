import logging
from pathlib import Path

from nova.config import load_config
from nova.lib.state import NovaState
from nova.slack import SlackPoster
from nova.tmux import has_window, send_keys, TMUX_SESSION

logger = logging.getLogger(__name__)

NOVA_DIR = Path.home() / ".nova"


class ExchangeHandler:
    def __init__(
        self,
        state_file: Path | None = None,
        config_path: Path | None = None,
    ):
        self._state_file = state_file or (NOVA_DIR / "state.json")
        self._poster: SlackPoster | None = None

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

        send_keys(tmux_target, text)
        print(f"[exchange] Routed reply to {tmux_window}: {text[:80]}")

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

    config = load_config(config_path)
    app_token = config["slack"].get("app_token")
    if not app_token:
        raise ValueError(
            "Slack app_token required for exchange. Set NOVA_SLACK_APP_TOKEN."
        )

    handler = ExchangeHandler(state_file=state_file, config_path=config_path)

    client = SocketModeClient(
        app_token=app_token,
        web_client=handler._poster._client if handler._poster else None,
        auto_reconnect_enabled=True,
        ping_interval=30,
        trace_enabled=True,
    )

    def process(client: SocketModeClient, req: SocketModeRequest):
        print(f"[exchange] << Event received: type={req.type} envelope={req.envelope_id[:12]}...")
        client.send_socket_mode_response(
            SocketModeResponse(envelope_id=req.envelope_id)
        )
        print(f"[exchange] >> Ack sent for {req.envelope_id[:12]}")

        if req.type != "events_api":
            print(f"[exchange] Skipping non-events_api: {req.type}")
            return

        event = req.payload.get("event", {})
        event_type = event.get("type", "unknown")
        subtype = event.get("subtype")
        thread_ts = event.get("thread_ts")
        text = event.get("text", "")
        user = event.get("user", "")
        channel = event.get("channel", "")
        ts = event.get("ts", "")

        print(f"[exchange] Event details: type={event_type} subtype={subtype} "
              f"channel={channel} ts={ts} thread_ts={thread_ts} user={user}")

        if event_type != "message":
            print(f"[exchange] Skipping: not a message event")
            return
        if subtype:
            print(f"[exchange] Skipping: message subtype={subtype}")
            return
        if not thread_ts:
            print(f"[exchange] Skipping: non-threaded message: {text[:50]}")
            return

        print(f"[exchange] Processing threaded reply from {user}: {text[:80]}")

        routed = handler.handle_message(
            channel=channel,
            thread_ts=thread_ts,
            message_ts=ts,
            text=text,
            user=user,
        )
        print(f"[exchange] Route result: {'delivered' if routed else 'not matched'}")

    client.socket_mode_request_listeners.append(process)

    print("[exchange] Connecting to Slack Socket Mode...")
    client.connect()
    print("[exchange] Connected. Listening for messages.")
    print(f"[exchange] Auto-reconnect: {client.auto_reconnect_enabled}")
    print(f"[exchange] Ping interval: {client.ping_interval}s")
    print(f"[exchange] Bot user ID filter: {handler._bot_user_id}")
    print("[exchange] Press Ctrl+C to stop.\n")

    import signal

    try:
        signal.pause()
    except KeyboardInterrupt:
        print("\n[exchange] Shutting down...")
        client.close()
        print("[exchange] Disconnected.")
