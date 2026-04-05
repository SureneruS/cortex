"""StopFailure hook — fires when a turn ends due to API error.

Sets runtime to error, stores error details, sends OS notification,
and blocks session on unrecoverable errors (billing, auth).
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone

ESCALATE_ERRORS = {"billing_error", "authentication_failed"}
NOTIFY_ERRORS = {"rate_limit", "server_error", "max_output_tokens"}


def _cortex_cli(*args: str) -> str | None:
    try:
        result = subprocess.run(
            ["cortex", "--json", *args], capture_output=True, text=True, timeout=5
        )
        return result.stdout if result.returncode == 0 else None
    except Exception:
        return None


def _session_name() -> str:
    cortex_id = os.environ.get("CORTEX_SESSION_ID", "")
    if not cortex_id:
        return "Unknown session"
    raw = _cortex_cli("session", "get", cortex_id)
    if raw:
        try:
            return json.loads(raw).get("name", cortex_id[:8])
        except (json.JSONDecodeError, TypeError):
            pass
    return cortex_id[:8]


def _notify(title: str, message: str) -> None:
    try:
        subprocess.run(
            [
                "terminal-notifier",
                "-title", "Cortex",
                "-subtitle", title,
                "-message", message,
                "-group", "cortex-error",
            ],
            capture_output=True,
            timeout=5,
        )
    except Exception:
        pass


def _send_human_message(content: str) -> None:
    _cortex_cli("session", "send", "human", content)


def handle_stop_failure(hook_input: dict) -> dict:
    cortex_session_id = os.environ.get("CORTEX_SESSION_ID")
    if not cortex_session_id:
        return {}

    error_type = hook_input.get("error", "unknown")
    error_details = hook_input.get("error_details", "")
    name = _session_name()
    now = datetime.now(timezone.utc).isoformat()

    update_data: dict = {
        "runtime": "error",
        "last_error": {
            "type": error_type,
            "details": str(error_details)[:500] if error_details else "",
            "at": now,
        },
    }

    if error_type in ESCALATE_ERRORS:
        update_data["status"] = "blocked"

    _cortex_cli(
        "session", "update", cortex_session_id,
        "--data", json.dumps(update_data),
        "--trigger", "stop_failure",
    )

    if error_type in ESCALATE_ERRORS:
        msg = f"Session '{name}' hit {error_type} — blocked and needs attention"
        _notify("Error", msg)
        _send_human_message(msg)
    elif error_type in NOTIFY_ERRORS:
        _notify(name, f"{error_type}: {str(error_details)[:100]}")

    return {}


def main():
    hook_input = json.loads(sys.stdin.read())
    result = handle_stop_failure(hook_input)
    print(json.dumps(result))
