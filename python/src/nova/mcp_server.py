import json
import os
from datetime import datetime, timezone
from pathlib import Path

import yaml
from mcp.server.fastmcp import FastMCP

from nova.slack import SlackPoster

mcp = FastMCP("arc")

_poster: SlackPoster | None = None
_dm_channel: str | None = None
_sender_name: str | None = None

CONFIG_PATH = Path.home() / ".nova" / "config.yaml"
DM_LOG_PATH = Path.home() / ".nova" / "dm_log.jsonl"


def _load_coworkers() -> dict[str, str]:
    if not CONFIG_PATH.exists():
        return {}
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)
    return config.get("slack", {}).get("coworkers", {})


def _init() -> tuple[SlackPoster, str]:
    global _poster, _dm_channel, _sender_name
    if _poster and _dm_channel:
        return _poster, _dm_channel
    token = os.environ["SLACK_BOT_TOKEN"]
    user_id = os.environ["SLACK_TARGET_USER_ID"]
    _sender_name = os.environ.get("ARC_SENDER_NAME")
    _poster = SlackPoster(bot_token=token, target_user_id=user_id)
    _dm_channel = _poster.get_dm_channel()
    return _poster, _dm_channel


@mcp.tool()
def send_message(text: str) -> str:
    """Send a DM to Suren as Arc."""
    poster, channel = _init()
    ts = poster.post_notification(channel=channel, text=text, username=_sender_name)
    return f"Sent. ts={ts}"


@mcp.tool()
def send_dm(name: str, text: str) -> str:
    """Send a DM to a coworker as Arc. Use lowercase first name (e.g. 'shubham')."""
    poster, _ = _init()
    coworkers = _load_coworkers()
    name_lower = name.lower()
    if name_lower not in coworkers:
        available = ", ".join(sorted(coworkers.keys()))
        return f"Unknown coworker '{name}'. Available: {available}"
    user_id = coworkers[name_lower]
    dm_channel = poster.open_dm(user_id)
    ts = poster.post_notification(channel=dm_channel, text=text, username="Arc")
    entry = {
        "action": "send_dm",
        "ts": ts,
        "channel": dm_channel,
        "to": name_lower,
        "to_id": user_id,
        "text": text,
        "sent_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(DM_LOG_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")
    return f"Sent DM to {name}. ts={ts}"


@mcp.tool()
def reply_to_thread(thread_ts: str, text: str) -> str:
    """Reply to a thread in Suren's DM."""
    poster, channel = _init()
    ts = poster.post_reply(
        channel=channel, thread_ts=thread_ts, text=text, username=_sender_name
    )
    return f"Replied. ts={ts}"


@mcp.tool()
def reply_to_dm(name: str, thread_ts: str, text: str) -> str:
    """Reply to a thread in a coworker's DM. Use the ts from send_dm as thread_ts."""
    poster, _ = _init()
    coworkers = _load_coworkers()
    name_lower = name.lower()
    if name_lower not in coworkers:
        available = ", ".join(sorted(coworkers.keys()))
        return f"Unknown coworker '{name}'. Available: {available}"
    user_id = coworkers[name_lower]
    dm_channel = poster.open_dm(user_id)
    ts = poster.post_reply(
        channel=dm_channel, thread_ts=thread_ts, text=text, username="Arc"
    )
    entry = {
        "action": "reply_to_dm",
        "ts": ts,
        "thread_ts": thread_ts,
        "channel": dm_channel,
        "to": name_lower,
        "to_id": user_id,
        "text": text,
        "sent_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(DM_LOG_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")
    return f"Replied to {name}'s thread. ts={ts}"


@mcp.tool()
def read_dm(name: str, limit: int = 5) -> list[dict]:
    """Read recent messages from a coworker's DM conversation."""
    poster, _ = _init()
    coworkers = _load_coworkers()
    name_lower = name.lower()
    if name_lower not in coworkers:
        available = ", ".join(sorted(coworkers.keys()))
        return [{"error": f"Unknown coworker '{name}'. Available: {available}"}]
    user_id = coworkers[name_lower]
    dm_channel = poster.open_dm(user_id)
    messages = poster.get_history(channel=dm_channel, limit=limit)
    entry = {
        "action": "read_dm",
        "channel": dm_channel,
        "target": name_lower,
        "target_id": user_id,
        "message_count": len(messages),
        "read_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(DM_LOG_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")
    return messages


@mcp.tool()
def read_dm_thread(name: str, thread_ts: str) -> list[dict]:
    """Read replies from a thread in a coworker's DM."""
    poster, _ = _init()
    coworkers = _load_coworkers()
    name_lower = name.lower()
    if name_lower not in coworkers:
        available = ", ".join(sorted(coworkers.keys()))
        return [{"error": f"Unknown coworker '{name}'. Available: {available}"}]
    user_id = coworkers[name_lower]
    dm_channel = poster.open_dm(user_id)
    messages = poster.get_replies(channel=dm_channel, thread_ts=thread_ts)
    entry = {
        "action": "read_dm_thread",
        "thread_ts": thread_ts,
        "channel": dm_channel,
        "target": name_lower,
        "target_id": user_id,
        "message_count": len(messages),
        "read_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(DM_LOG_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")
    return messages


@mcp.tool()
def add_reaction(timestamp: str, emoji: str) -> str:
    """Add a reaction to a message in Suren's DM."""
    poster, channel = _init()
    poster.add_reaction(channel=channel, timestamp=timestamp, emoji=emoji)
    return "Reaction added."


@mcp.tool()
def read_replies(thread_ts: str) -> list[dict]:
    """Read replies from a thread in Suren's DM."""
    poster, channel = _init()
    return poster.get_replies(channel=channel, thread_ts=thread_ts)


def main():
    mcp.run()
