"""Structured status event emission for worker observability (CTX-67).

Workers emit events via channels so control sessions know what's happening.
Events are sent to the parent session (CORTEX_PARENT_NAME) if set.
Registry is also updated so dashboard/list/health see the state.
"""

import json
import os
import subprocess
from datetime import datetime, timezone

# Map status events to runtime states for the session registry.
# "done" is omitted — session_end hook handles closing.
_EVENT_TO_RUNTIME: dict[str, str] = {
    "started": "working",
    "editing_file": "working",
    "committed": "working",
    "progress": "working",
    "turn_completed": "waiting_input",
    "error": "error",
}


def _update_session_runtime(session_id: str, runtime: str) -> None:
    """Fire-and-forget update of this session's runtime state in the registry."""
    data = json.dumps({"runtime": runtime})
    try:
        subprocess.Popen(
            ["cortex", "--json", "session", "update", session_id, "--data", data, "--trigger", "status-event"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


def emit_status_event(event: str, detail: str = "") -> None:
    """Emit a structured status event to the parent session via channels.

    Also updates the session's own runtime state in the registry so that
    dashboard, session list, and health checks reflect the current state.

    No-op if CORTEX_SESSION_NAME or CORTEX_PARENT_NAME is not set.
    Fire-and-forget — never blocks the hook or raises.
    """
    session_name = os.environ.get("CORTEX_SESSION_NAME")
    parent_name = os.environ.get("CORTEX_PARENT_NAME")
    if not session_name or not parent_name:
        return

    # Update registry runtime state (uses CORTEX_SESSION_ID, independent of parent)
    session_id = os.environ.get("CORTEX_SESSION_ID")
    runtime = _EVENT_TO_RUNTIME.get(event)
    if session_id and runtime:
        _update_session_runtime(session_id, runtime)

    content = json.dumps({
        "type": "status_event",
        "event": event,
        "detail": detail,
        "worker": session_name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    meta = json.dumps({"type": "status_event", "event": event})

    try:
        subprocess.Popen(
            ["cortex", "--json", "session", "message", parent_name, content, "--meta", meta],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass
