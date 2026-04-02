"""SessionEnd hook — fires when a CC session terminates.

Delegates to `cortex session close --from-hook` for terminal reasons,
which handles message expiry, registry update, and avoids close loops.

Non-terminal reasons (clear, resume) just record the event.
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone


def _cortex_cli(*args: str) -> str | None:
    try:
        result = subprocess.run(
            ["cortex", *args], capture_output=True, text=True, timeout=10
        )
        return result.stdout if result.returncode == 0 else None
    except Exception:
        return None


def _session_name(cortex_id: str) -> str:
    raw = _cortex_cli("session", "get", cortex_id)
    if raw:
        try:
            return json.loads(raw).get("name", cortex_id[:8])
        except (json.JSONDecodeError, TypeError):
            pass
    return cortex_id[:8]


def _notify(subtitle: str, message: str) -> None:
    try:
        subprocess.run(
            [
                "terminal-notifier",
                "-title", "Cortex",
                "-subtitle", subtitle,
                "-message", message,
                "-group", "cortex-session-end",
            ],
            capture_output=True,
            timeout=5,
        )
    except Exception:
        pass


KEEP_ACTIVE_REASONS = {"clear", "resume"}


def handle_session_end(hook_input: dict) -> dict:
    cortex_session_id = os.environ.get("CORTEX_SESSION_ID")
    if not cortex_session_id:
        return {}

    reason = hook_input.get("reason", "other")
    name = _session_name(cortex_session_id)
    now = datetime.now(timezone.utc).isoformat()

    if reason in KEEP_ACTIVE_REASONS:
        _cortex_cli(
            "session", "update", cortex_session_id,
            "--data", json.dumps({
                "last_session_end": {"reason": reason, "at": now},
            }),
            "--trigger", f"session_end_{reason}",
        )
        if reason == "clear":
            _notify(name, "Session cleared")
        return {}

    # Terminal reason — delegate to unified close path
    _cortex_cli("session", "close", cortex_session_id, "--from-hook")
    _notify("Session Ended", f"{name} finished ({reason})")

    return {}


def main():
    hook_input = json.loads(sys.stdin.read())
    result = handle_session_end(hook_input)
    print(json.dumps(result))
