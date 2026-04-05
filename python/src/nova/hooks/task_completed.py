"""TaskCompleted hook — fires when a task is marked completed.

Updates registry: updates task count.
Side-effect only — no context injection.
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone

from nova.hooks.status_event import emit_status_event


def _cortex_cli(*args: str) -> str | None:
    try:
        result = subprocess.run(
            ["cortex", "--json", *args], capture_output=True, text=True, timeout=5
        )
        return result.stdout if result.returncode == 0 else None
    except Exception:
        return None


def handle_task_completed(hook_input: dict) -> dict:
    cortex_session_id = os.environ.get("CORTEX_SESSION_ID")
    if not cortex_session_id:
        return {}

    total_tasks = hook_input.get("total_tasks", 0)
    completed_tasks = hook_input.get("completed_tasks", 0)

    update_data: dict = {
        "last_task_completed_at": datetime.now(timezone.utc).isoformat(),
    }
    if total_tasks:
        update_data["task_count"] = total_tasks
    if completed_tasks:
        update_data["tasks_completed"] = completed_tasks

    _cortex_cli(
        "session", "update", cortex_session_id,
        "--data", json.dumps(update_data),
        "--trigger", "task_completed",
    )

    if completed_tasks > 0:
        emit_status_event("progress", f"Task completed ({completed_tasks}/{total_tasks})")

    return {}


def main():
    hook_input = json.loads(sys.stdin.read())
    result = handle_task_completed(hook_input)
    print(json.dumps(result))
