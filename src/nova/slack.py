from slack_sdk import WebClient


class SlackPoster:
    def __init__(self, bot_token: str, target_user_id: str):
        self._client = WebClient(token=bot_token)
        self._target_user_id = target_user_id

    def get_dm_channel(self) -> str:
        resp = self._client.conversations_open(users=[self._target_user_id])
        return resp["channel"]["id"]

    def post_notification(
        self,
        channel: str,
        text: str,
        thread_ts: str | None = None,
        username: str | None = None,
    ) -> str:
        kwargs: dict = {"channel": channel, "text": text}
        if thread_ts:
            kwargs["thread_ts"] = thread_ts
        if username:
            kwargs["username"] = username
        resp = self._client.chat_postMessage(**kwargs)
        return resp["ts"]

    def add_reaction(self, channel: str, timestamp: str, emoji: str) -> None:
        self._client.reactions_add(
            channel=channel, timestamp=timestamp, name=emoji
        )

    def post_reply(
        self, channel: str, thread_ts: str, text: str, username: str | None = None
    ) -> str:
        return self.post_notification(
            channel, text, thread_ts=thread_ts, username=username
        )

    def get_replies(self, channel: str, thread_ts: str) -> list[dict]:
        resp = self._client.conversations_replies(channel=channel, ts=thread_ts)
        return [
            {"user": m.get("user", ""), "text": m.get("text", ""), "ts": m["ts"]}
            for m in resp["messages"]
        ]
