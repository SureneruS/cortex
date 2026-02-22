import json
from pathlib import Path
from typing import TypedDict


class SessionState(TypedDict):
    repos: list[str]
    transcript_path: str
    memory_injected: bool
    goal: str | None


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

    def register_session(self, session_id: str, repos: list[str], transcript_path: str):
        if session_id not in self.sessions:
            self.sessions[session_id] = SessionState(
                repos=repos,
                transcript_path=transcript_path,
                memory_injected=False,
                goal=None,
            )

    def mark_injected(self, session_id: str, goal: str):
        if session_id in self.sessions:
            self.sessions[session_id]["memory_injected"] = True
            self.sessions[session_id]["goal"] = goal

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
                },
                indent=2,
            )
            + "\n"
        )
        tmp.rename(self._path)
