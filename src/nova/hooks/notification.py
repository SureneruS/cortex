import json
import logging
import sys
from pathlib import Path

from nova.config import load_config
from nova.lib.state import NovaState
from nova.slack import SlackPoster
from nova.tmux import is_client_attached

logger = logging.getLogger(__name__)

NOVA_DIR = Path.home() / ".nova"


def _format_message(session: dict, hook_input: dict) -> str:
    window = session.get("tmux_window", "unknown")
    goal = session.get("goal", "")

    lines = [f"*[{window}]* Waiting for input"]
    if goal:
        lines.append(f"Goal: {goal}")
    lines.append("")
    lines.append("_Reply here to send input_")

    return "\n".join(lines)


def handle_notification(
    hook_input: dict,
    state_file: Path | None = None,
    config_path: Path | None = None,
) -> dict:
    if state_file is None:
        state_file = NOVA_DIR / "state.json"

    session_id = hook_input.get("session_id", "")
    if not session_id or not state_file.exists():
        return {}

    state = NovaState(state_file)
    session = state.sessions.get(session_id)
    if not session:
        return {}

    tmux_target = session.get("tmux_target")
    if not tmux_target:
        return {}

    if is_client_attached(tmux_target):
        return {}

    config = load_config(config_path)
    slack_config = config["slack"]
    poster = SlackPoster(
        bot_token=slack_config["bot_token"],
        target_user_id=slack_config.get("target_user_id", ""),
    )

    channel = session.get("slack_channel")
    if not channel:
        channel = state.slack_config.get("dm_channel")
    if not channel:
        channel = poster.get_dm_channel()
        state.set_slack_config(dm_channel=channel)

    thread_ts = session.get("slack_thread_ts")
    text = _format_message(session, hook_input)

    new_ts = poster.post_notification(
        channel=channel,
        text=text,
        thread_ts=thread_ts,
    )

    if not thread_ts:
        state.set_slack_thread(session_id, thread_ts=new_ts, channel=channel)
    state.save()

    return {}


def main():
    hook_input = json.loads(sys.stdin.read())
    result = handle_notification(hook_input)
    print(json.dumps(result))
