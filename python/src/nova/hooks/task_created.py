"""TaskCreated hook — fires when TaskCreate tool is used.

Updates registry: stores current task count, last task subject.
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


def handle_task_created(hook_input: dict) -> dict:
    cortex_session_id = os.environ.get("CORTEX_SESSION_ID")
    if not cortex_session_id:
        return {}

    subject = hook_input.get("task", {}).get("subject", "")
    total_tasks = hook_input.get("total_tasks", 0)

    update_data: dict = {
        "last_task_at": datetime.now(timezone.utc).isoformat(),
    }
    if subject:
        update_data["last_task_subject"] = subject[:200]
    if total_tasks:
        update_data["task_count"] = total_tasks

    _cortex_cli(
        "session", "update", cortex_session_id,
        "--data", json.dumps(update_data),
        "--trigger", "task_created",
    )

    return {}


def main():
    hook_input = json.loads(sys.stdin.read())
    result = handle_task_created(hook_input)
    print(json.dumps(result))
