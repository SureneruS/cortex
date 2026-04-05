"""Structured status event emission for worker observability (CTX-67).

Workers emit events via channels so control sessions know what's happening.
Events are sent to the parent session (CORTEX_PARENT_NAME) if set.
"""

import json
import os
import subprocess
from datetime import datetime, timezone


def emit_status_event(event: str, detail: str = "") -> None:
    """Emit a structured status event to the parent session via channels.

    No-op if CORTEX_SESSION_NAME or CORTEX_PARENT_NAME is not set.
    Fire-and-forget — never blocks the hook or raises.
    """
    session_name = os.environ.get("CORTEX_SESSION_NAME")
    parent_name = os.environ.get("CORTEX_PARENT_NAME")
    if not session_name or not parent_name:
        return

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
