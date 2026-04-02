"""PostCompact hook — fires after context compaction.

Updates registry: increments compact_count, stores timestamp.
Re-injects workflow context so it survives compaction.
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def _cortex_cli(*args: str) -> str | None:
    try:
        result = subprocess.run(
            ["cortex", *args], capture_output=True, text=True, timeout=5
        )
        return result.stdout if result.returncode == 0 else None
    except Exception:
        return None


def _load_workflow_context() -> str | None:
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT", "")
    if plugin_root:
        ctx_path = Path(plugin_root) / "hooks" / "workflow-context.md"
    else:
        ctx_path = Path(__file__).parents[4] / "plugin" / "hooks" / "workflow-context.md"

    try:
        return ctx_path.read_text()
    except (FileNotFoundError, PermissionError):
        return None


def handle_post_compact(hook_input: dict) -> dict:
    cortex_session_id = os.environ.get("CORTEX_SESSION_ID")
    if cortex_session_id:
        _cortex_cli(
            "session", "update", cortex_session_id,
            "--data", json.dumps({
                "last_compaction_completed": datetime.now(timezone.utc).isoformat(),
            }),
            "--trigger", "post_compact",
            "--increment", "compact_count",
        )

    result: dict = {}
    workflow_ctx = _load_workflow_context()
    if workflow_ctx:
        result["hookSpecificOutput"] = {
            "hookEventName": "PostCompact",
            "additionalContext": workflow_ctx,
        }
    return result


def main():
    hook_input = json.loads(sys.stdin.read())
    result = handle_post_compact(hook_input)
    print(json.dumps(result))
