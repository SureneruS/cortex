import os

from mcp.server.fastmcp import FastMCP

from nova.slack import SlackPoster

mcp = FastMCP("arc")

_poster: SlackPoster | None = None
_dm_channel: str | None = None
_sender_prefix: str | None = None


def _init() -> tuple[SlackPoster, str]:
    global _poster, _dm_channel, _sender_prefix
    if _poster and _dm_channel:
        return _poster, _dm_channel
    token = os.environ["SLACK_BOT_TOKEN"]
    user_id = os.environ["SLACK_TARGET_USER_ID"]
    _sender_prefix = os.environ.get("ARC_SENDER_PREFIX")
    _poster = SlackPoster(bot_token=token, target_user_id=user_id)
    _dm_channel = _poster.get_dm_channel()
    return _poster, _dm_channel


def _format(text: str) -> str:
    if _sender_prefix:
        return f"[{_sender_prefix}] {text}"
    return text


@mcp.tool()
def send_message(text: str) -> str:
    """Send a DM to Suren as Arc."""
    poster, channel = _init()
    ts = poster.post_notification(channel=channel, text=_format(text))
    return f"Sent. ts={ts}"


@mcp.tool()
def reply_to_thread(thread_ts: str, text: str) -> str:
    """Reply to a thread in Suren's DM."""
    poster, channel = _init()
    ts = poster.post_reply(channel=channel, thread_ts=thread_ts, text=_format(text))
    return f"Replied. ts={ts}"


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
