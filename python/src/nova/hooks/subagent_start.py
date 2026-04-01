"""SubagentStart hook — fires when a subagent (Agent tool) is spawned.

Updates registry: increments subagent_count, stores agent_type.
Side-effect only — no context injection.
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


def handle_subagent_start(hook_input: dict) -> dict:
    cortex_session_id = os.environ.get("CORTEX_SESSION_ID")
    if not cortex_session_id:
        return {}

    agent_type = hook_input.get("agent_type", "unknown")

    _cortex_cli(
        "session", "update", cortex_session_id,
        "--data", json.dumps({
            "last_subagent": {
                "type": agent_type,
                "started_at": datetime.now(timezone.utc).isoformat(),
            },
        }),
        "--trigger", "subagent_start",
        "--increment", "subagent_count",
    )

    return {}


def main():
    hook_input = json.loads(sys.stdin.read())
    result = handle_subagent_start(hook_input)
    print(json.dumps(result))
