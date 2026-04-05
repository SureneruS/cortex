"""SessionEnd hook — fires when a CC session terminates.

Transitions:
- clear: keep active (new CC session about to start)
- resume: pause (switching to different conversation)
- exit/logout/other: pause (CC exited, session recoverable)
- If status is already completed/closed: no-op (cortex close set it first)
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone

from nova.hooks.status_event import emit_status_event


def _cortex_update(session_id: str, data: dict, trigger: str) -> None:
    """Single fast CLI call to update session. Fire-and-forget."""
    try:
        subprocess.Popen(
            ["cortex", "--json", "session", "update", session_id,
             "--data", json.dumps(data),
             "--trigger", trigger],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


KEEP_ACTIVE_REASONS = {"clear"}


def handle_session_end(hook_input: dict) -> dict:
    cortex_session_id = os.environ.get("CORTEX_SESSION_ID")
    if not cortex_session_id:
        return {}

    reason = hook_input.get("reason", "other")
    now = datetime.now(timezone.utc).isoformat()
    name = os.environ.get("CORTEX_SESSION_NAME", cortex_session_id[:8])

    if reason in KEEP_ACTIVE_REASONS:
        _cortex_update(
            cortex_session_id,
            {"last_session_end": {"reason": reason, "at": now}},
            f"session_end_{reason}",
        )
        return {}

    # All other reasons (exit, resume, logout, etc.) → paused
    # Uses Popen (fire-and-forget) so CC doesn't have to wait.
    # If cortex close already set completed/closed, the update will be
    # rejected by the state machine validator (completed/closed → paused is invalid).
    _cortex_update(
        cortex_session_id,
        {"status": "paused", "last_session_end": {"reason": reason, "at": now}},
        f"session_end_{reason}",
    )

    emit_status_event("done", f"Session ended: {reason}")

    return {}


def main():
    hook_input = json.loads(sys.stdin.read())
    result = handle_session_end(hook_input)
    print(json.dumps(result))
