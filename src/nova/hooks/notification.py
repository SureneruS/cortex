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


def _capture_pane_context(tmux_target: str) -> str | None:
    import subprocess

    result = subprocess.run(
        ["tmux", "capture-pane", "-t", tmux_target, "-p"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    lines = result.stdout.strip().split("\n")
    relevant = [line for line in lines if line.strip()][-15:]
    return "\n".join(relevant)


def _format_message(session: dict, hook_input: dict) -> str:
    window = session.get("tmux_window", "unknown")
    notification_type = hook_input.get("notification_type", "")
    message = hook_input.get("message", "")

    if notification_type == "permission_prompt":
        lines = [f"*[{window}]* Permission needed"]
        lines.append(f"_{message}_")

        tmux_target = session.get("tmux_target")
        if tmux_target:
            pane = _capture_pane_context(tmux_target)
            if pane:
                lines.append(f"```{pane}```")

        lines.append("")
        lines.append("Reply *y* to allow, *n* to deny")
        return "\n".join(lines)

    lines = [f"*[{window}]* Waiting for input"]
    goal = session.get("goal", "")
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
    log_file = NOVA_DIR / "logs" / "notification.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)

    raw = sys.stdin.read()
    try:
        hook_input = json.loads(raw)
    except Exception as e:
        log_file.open("a").write(f"PARSE ERROR: {e}\nraw={raw[:500]}\n\n")
        print(json.dumps({}))
        return

    log_file.open("a").write(f"CALLED: {json.dumps(hook_input, indent=2)}\n\n")

    try:
        result = handle_notification(hook_input)
    except Exception as e:
        import traceback
        log_file.open("a").write(f"ERROR: {traceback.format_exc()}\n\n")
        print(json.dumps({}))
        return

    log_file.open("a").write(f"RESULT: {json.dumps(result)}\n\n")
    print(json.dumps(result))
