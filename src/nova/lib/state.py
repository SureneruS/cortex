import json
from pathlib import Path
from typing import Any


class NovaState:
    def __init__(self, path: Path):
        self._path = path
        data = json.loads(path.read_text()) if path.exists() else {}
        self.last_dream_run: str | None = data.get("last_dream_run")
        self.sessions: dict[str, Any] = data.get("sessions", {})

    def register_session(self, session_id: str, repos: list[str], transcript_path: str):
        if session_id not in self.sessions:
            self.sessions[session_id] = {
                "repos": repos,
                "transcript_path": transcript_path,
                "memory_injected": False,
                "goal": None,
            }

    def mark_injected(self, session_id: str, goal: str):
        if session_id in self.sessions:
            self.sessions[session_id]["memory_injected"] = True
            self.sessions[session_id]["goal"] = goal

    def save(self):
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(
                {
                    "last_dream_run": self.last_dream_run,
                    "sessions": self.sessions,
                },
                indent=2,
            )
            + "\n"
        )
        tmp.rename(self._path)
