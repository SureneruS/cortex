from __future__ import annotations

import json
import shutil
import subprocess
import time
import uuid
from pathlib import Path

from nova.lib.log import nova_log as _log
from nova.lib.state import NovaState
from nova.slack import SlackPoster
from nova.tmux import (
    TMUX_SESSION,
    has_window,
    is_client_attached,
    send_keys,
)

NOVA_DIR = Path.home() / ".nova"


class RotationManager:
    def __init__(
        self,
        state_file: Path | None = None,
        poster: SlackPoster | None = None,
        config: dict | None = None,
    ):
        self._state_file = state_file or (NOVA_DIR / "state.json")
        self._poster = poster
        self._config = config or {}
        self._pending: dict[str, float] = {}

    def check_and_rotate(self, idle_sessions: dict[str, float]):
        threshold = self._config.get("idle_threshold_minutes", 30) * 60
        warning_delay = self._config.get("warning_delay_seconds", 120)

        if not self._state_file.exists():
            return

        try:
            state = NovaState(self._state_file)
        except Exception:
            return

        for sid, idle_secs in idle_sessions.items():
            session = state.sessions.get(sid)
            if not session:
                continue
            if session.get("status", "active") != "active":
                continue
            if not session.get("tmux_window"):
                continue
            if not session.get("slack_thread_ts"):
                continue

            tmux_target = session.get("tmux_target", "")
            if is_client_attached(tmux_target):
                self._pending.pop(sid, None)
                continue

            if idle_secs < threshold:
                self._pending.pop(sid, None)
                continue

            if sid not in self._pending:
                self._pending[sid] = time.time() + warning_delay
                if self._poster:
                    window = session.get("tmux_window", "unknown")
                    mins = int(idle_secs // 60)
                    self._poster.post_reply(
                        channel=session["slack_channel"],
                        thread_ts=session["slack_thread_ts"],
                        text=f"*[{window}]* Idle for {mins} min. Rotating in {warning_delay // 60} min — reply *HOLD* to cancel.",
                    )
                _log(f"[rotation] Warning posted for {sid[:8]}, rotating at {self._pending[sid]}")
                continue

            if time.time() < self._pending[sid]:
                continue

            _log(f"[rotation] Rotating session {sid[:8]}...")
            self._pending.pop(sid)
            self._rotate_session(sid, session)

    def cancel_rotation(self, session_id: str):
        if session_id in self._pending:
            self._pending.pop(session_id)
            _log(f"[rotation] Rotation cancelled for {session_id[:8]}")

    def rotate_now(self, session_id: str):
        if not self._state_file.exists():
            return

        state = NovaState(self._state_file)
        session = state.sessions.get(session_id)
        if not session:
            _log(f"[rotation] Session {session_id} not found")
            return

        self._rotate_session(session_id, session)

    def _rotate_session(self, session_id: str, session: dict):
        tmux_target = session.get("tmux_target", "")
        tmux_window = session.get("tmux_window", "")
        transcript_path = session.get("transcript_path", "")
        channel = session.get("slack_channel", "")
        thread_ts = session.get("slack_thread_ts", "")
        chain_id = session.get("chain_id") or str(uuid.uuid4())
        chain_sequence = session.get("chain_sequence", 1)
        repos = session.get("repos", [])

        if not has_window(TMUX_SESSION, tmux_window):
            _log(f"[rotation] Window {tmux_window} no longer exists, skipping")
            return

        _log(f"[rotation] Sending /rotate-prep to {tmux_window}...")
        rotate_timeout = self._config.get("rotate_prep_timeout_seconds", 300)
        self._send_command_and_wait(tmux_target, "/rotate-prep", transcript_path, timeout=rotate_timeout)

        handoff_context = self._extract_last_assistant_text(transcript_path)
        if not handoff_context:
            handoff_context = f"Continuing work on: {session.get('goal', 'unknown goal')}"
        if len(handoff_context) > 10000:
            handoff_context = handoff_context[:10000] + "\n\n...(truncated)"

        _log(f"[rotation] Killing {tmux_window}...")
        subprocess.run(
            ["tmux", "kill-window", "-t", f"{TMUX_SESSION}:{tmux_window}"],
            capture_output=True,
        )

        state = NovaState(self._state_file)
        state.set_status(session_id, "rotated")
        state.save()

        _log(f"[rotation] Starting fresh session {tmux_window}...")
        repo_path = ""
        if repos:
            for candidate in [
                Path.home() / "workspace" / "cercli" / repos[0],
                Path.home() / "workspace" / repos[0],
            ]:
                if candidate.exists():
                    repo_path = str(candidate)
                    break

        if not repo_path:
            _log(f"[rotation] Could not resolve repo path for {repos}, using home")
            repo_path = str(Path.home())

        nova_bin = shutil.which("nova") or "nova"
        subprocess.Popen(
            [nova_bin, "start", repo_path, "--name", tmux_window, handoff_context],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        new_seq = chain_sequence + 1
        if self._poster and channel and thread_ts:
            self._poster.post_reply(
                channel=channel,
                thread_ts=thread_ts,
                text=f"Session rotated. Chain: {tmux_window} #{new_seq}",
            )

        _log(f"[rotation] Session {tmux_window} rotated -> chain #{new_seq}")

    def _send_command_and_wait(
        self, target: str, command: str, transcript_path: str, timeout: int = 180
    ) -> bool:
        stable_threshold = self._config.get("stable_seconds", 5)
        path = Path(transcript_path)
        initial_size = path.stat().st_size if path.exists() else 0

        send_keys(target, command)

        deadline = time.time() + timeout
        last_size = initial_size
        last_change_time = time.time()
        started_growing = False

        while time.time() < deadline:
            time.sleep(0.5)
            current_size = path.stat().st_size if path.exists() else 0

            if current_size > initial_size and not started_growing:
                started_growing = True

            if current_size != last_size:
                last_size = current_size
                last_change_time = time.time()
            elif started_growing and (time.time() - last_change_time) >= stable_threshold:
                return True

        _log(f"[rotation] Timeout waiting for {command} response")
        return False

    def _extract_last_assistant_text(self, transcript_path: str) -> str:
        path = Path(transcript_path)
        if not path.exists():
            return ""

        last_text = ""
        try:
            for line in path.read_text().splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                msg = entry.get("message", {})
                if msg.get("role") != "assistant":
                    continue
                content = msg.get("content", [])
                if isinstance(content, list):
                    parts = [
                        item.get("text", "")
                        for item in content
                        if isinstance(item, dict) and item.get("type") == "text"
                    ]
                    text = "\n".join(parts)
                    if text.strip():
                        last_text = text
        except Exception:
            pass

        return last_text


class DreamScheduler:
    def __init__(
        self,
        nova_dir: Path | None = None,
        capture_threshold: int = 3,
        check_interval_hours: int = 24,
    ):
        self._nova_dir = nova_dir or NOVA_DIR
        self._threshold = capture_threshold
        self._interval_secs = check_interval_hours * 3600
        self._last_run: float | None = None

    def maybe_run(self):
        if self._last_run is not None:
            elapsed = time.time() - self._last_run
            if elapsed < self._interval_secs:
                return

        captures_dir = self._nova_dir / "memory" / "captures"
        if not captures_dir.is_dir():
            return

        captures = list(captures_dir.glob("*.md"))
        if len(captures) < self._threshold:
            return

        _log(f"[dream] {len(captures)} captures found (threshold={self._threshold}), spawning dream agent...")
        nova_bin = shutil.which("nova") or "nova"
        subprocess.Popen(
            [nova_bin, "start", str(self._nova_dir), "--name", "dream", "--agent", "dream",
             "Process all pending captures in ~/.nova/memory/captures/ into knowledge files."],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self._last_run = time.time()
