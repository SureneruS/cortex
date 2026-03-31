"""Stop hook — fires after each assistant turn completes.

Updates runtime to waiting_input, increments turn count,
and stores last_assistant_message for session watch.
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone


def _cortex_cli(*args: str) -> str | None:
    try:
        result = subprocess.run(
            ["cortex", *args], capture_output=True, text=True, timeout=5
        )
        return result.stdout if result.returncode == 0 else None
    except Exception:
        return None


def handle_stop(hook_input: dict) -> dict:
    cortex_session_id = os.environ.get("CORTEX_SESSION_ID")
    if not cortex_session_id:
        return {}

    last_message = hook_input.get("last_assistant_message", "")

    # Truncate for storage — full message can be huge
    snippet = last_message[:2000] if last_message else ""

    update_data: dict = {
        "runtime": "waiting_input",
        "last_turn_at": datetime.now(timezone.utc).isoformat(),
    }
    if snippet:
        update_data["last_response_snippet"] = snippet

    _cortex_cli(
        "session", "update", cortex_session_id,
        "--data", json.dumps(update_data),
        "--trigger", "stop_hook",
        "--increment", "turn_count",
    )

    return {}


def main():
    hook_input = json.loads(sys.stdin.read())
    result = handle_stop(hook_input)
    print(json.dumps(result))
