"""Structured status event emission for worker observability (CTX-67).

Workers emit events via channels so control sessions know what's happening.
Major events push to parent session; all events update the session registry.
"""

import json
import os
import subprocess
from datetime import datetime, timezone

# Major events push a channel message to the parent session.
# Minor events only update the registry (no channel spam).
MAJOR_EVENTS = {"started", "done", "error", "blocked"}

# Tests set this to True to bypass the PYTEST_CURRENT_TEST guard.
_TESTING_OVERRIDE = False

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
    """Emit a structured status event.

    All events update the session registry (last_event + runtime).
    Only major lifecycle events (started, done, error, blocked) push
    a channel message to the parent.

    No-op if CORTEX_SESSION_NAME is not set.
    Fire-and-forget — never blocks the hook or raises.
    """
    session_name = os.environ.get("CORTEX_SESSION_NAME")
    if not session_name:
        return

    # Don't emit real events during test runs (pytest sets PYTEST_CURRENT_TEST).
    # Tests that need to exercise this function patch _TESTING_OVERRIDE.
    if os.environ.get("PYTEST_CURRENT_TEST") and not _TESTING_OVERRIDE:
        return

    now = datetime.now(timezone.utc).isoformat()

    # Always update the registry with the latest event
    registry_data = json.dumps({
        "last_event": event,
        "last_event_detail": detail[:200] if detail else "",
        "last_event_at": now,
    })
    try:
        subprocess.Popen(
            ["cortex", "--json", "session", "update", session_name,
             "--data", registry_data, "--trigger", f"hook:{event}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass

    # Update registry runtime state (independent of parent)
    session_id = os.environ.get("CORTEX_SESSION_ID")
    runtime = _EVENT_TO_RUNTIME.get(event)
    if session_id and runtime:
        _update_session_runtime(session_id, runtime)

    # Only push channel message to parent for major lifecycle events
    parent_name = os.environ.get("CORTEX_PARENT_NAME")
    if not parent_name or event not in MAJOR_EVENTS:
        return

    content = json.dumps({
        "type": "status_event",
        "event": event,
        "detail": detail,
        "worker": session_name,
        "timestamp": now,
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
