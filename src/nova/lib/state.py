import json
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict


class SessionState(TypedDict):
    repos: list[str]
    transcript_path: str
    memory_injected: bool
    goal: str | None
    started_at: str
    last_active_at: str
    tmux_target: str | None
    tmux_window: str | None
    slack_thread_ts: str | None
    slack_channel: str | None
    chain_id: str | None
    chain_sequence: int
    parent_session_id: str | None
    compaction_count: int
    status: str


class NovaState:
    def __init__(self, path: Path):
        self._path = path
        if not path.exists():
            raise FileNotFoundError(
                f"Nova state file not found: {path}. Run 'nova-setup' to initialize."
            )
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, ValueError) as e:
            raise ValueError(f"Malformed state file {path}: {e}")

        self.last_dream_run: str | None = data.get("last_dream_run")
        self.sessions: dict[str, SessionState] = data.get("sessions", {})
        self.slack_config: dict = data.get("slack", {})

    def register_session(
        self,
        session_id: str,
        repos: list[str],
        transcript_path: str,
        tmux_target: str | None = None,
        tmux_window: str | None = None,
        chain_id: str | None = None,
        chain_sequence: int = 1,
        parent_session_id: str | None = None,
    ):
        now = datetime.now(timezone.utc).isoformat()
        if session_id not in self.sessions:
            self.sessions[session_id] = SessionState(
                repos=repos,
                transcript_path=transcript_path,
                memory_injected=False,
                goal=None,
                started_at=now,
                last_active_at=now,
                tmux_target=tmux_target,
                tmux_window=tmux_window,
                slack_thread_ts=None,
                slack_channel=None,
                chain_id=chain_id,
                chain_sequence=chain_sequence,
                parent_session_id=parent_session_id,
                compaction_count=0,
                status="active",
            )

    def mark_injected(self, session_id: str, goal: str):
        if session_id in self.sessions:
            self.sessions[session_id]["memory_injected"] = True
            self.sessions[session_id]["goal"] = goal
            self.sessions[session_id]["last_active_at"] = datetime.now(timezone.utc).isoformat()

    def set_slack_thread(self, session_id: str, thread_ts: str, channel: str):
        if session_id in self.sessions:
            self.sessions[session_id]["slack_thread_ts"] = thread_ts
            self.sessions[session_id]["slack_channel"] = channel

    def find_session_by_thread(self, thread_ts: str) -> tuple[str, SessionState] | None:
        for sid, session in self.sessions.items():
            if session.get("slack_thread_ts") == thread_ts:
                return (sid, session)
        return None

    def increment_compaction(self, session_id: str):
        if session_id in self.sessions:
            self.sessions[session_id]["compaction_count"] = (
                self.sessions[session_id].get("compaction_count", 0) + 1
            )

    def set_status(self, session_id: str, status: str):
        if session_id in self.sessions:
            self.sessions[session_id]["status"] = status

    def find_sessions_by_chain(self, chain_id: str) -> list[tuple[str, SessionState]]:
        return [
            (sid, session)
            for sid, session in self.sessions.items()
            if session.get("chain_id") == chain_id
        ]

    def set_slack_config(
        self, dm_channel: str | None = None, bot_user_id: str | None = None
    ):
        if dm_channel is not None:
            self.slack_config["dm_channel"] = dm_channel
        if bot_user_id is not None:
            self.slack_config["bot_user_id"] = bot_user_id

    def save(self):
        """Atomic write via tmp file + rename. Last writer wins on concurrent access,
        which is fine — hooks run sequentially per session."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(
                {
                    "last_dream_run": self.last_dream_run,
                    "sessions": self.sessions,
                    "slack": self.slack_config,
                },
                indent=2,
            )
            + "\n"
        )
        tmp.rename(self._path)
