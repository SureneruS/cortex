"""PostToolUse hook for workflow file tracking.

Detects when workflow artifacts (contracts, plans) are created or updated.
Captures lifecycle transitions to cortex session metadata.
"""

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone


def _cortex_cli(*args: str) -> str | None:
    try:
        result = subprocess.run(
            ["cortex", "--json", *args], capture_output=True, text=True, timeout=5
        )
        return result.stdout if result.returncode == 0 else None
    except Exception:
        return None


# Patterns for workflow artifacts
WORKFLOW_PATTERNS = {
    "contracts": re.compile(r"contracts-[\w-]+\.md$"),
    "plan": re.compile(r"plan-[\w-]+\.md$"),
}


def _detect_artifact(file_path: str) -> tuple[str | None, str | None]:
    """Detect if a file is a workflow artifact. Returns (type, slug) or (None, None)."""
    for artifact_type, pattern in WORKFLOW_PATTERNS.items():
        match = pattern.search(file_path)
        if match:
            # Extract slug from filename
            basename = os.path.basename(file_path)
            slug_match = re.match(r"(?:contracts|plan)-([\w-]+)\.md$", basename)
            slug = slug_match.group(1) if slug_match else "unknown"
            return artifact_type, slug
    return None, None


def _phase_from_artifact(artifact_type: str) -> str:
    return {
        "contracts": "align",
        "plan": "plan",
    }.get(artifact_type, "unknown")


def handle_workflow_file(hook_input: dict) -> dict:
    file_path = hook_input.get("tool_input", {}).get("file_path", "")
    if not file_path:
        # Try env var fallback
        file_path = os.environ.get("CLAUDE_FILE_PATH", "")

    if not file_path:
        return {}

    artifact_type, slug = _detect_artifact(file_path)
    if not artifact_type:
        return {}

    cortex_session_id = os.environ.get("CORTEX_SESSION_ID")
    if not cortex_session_id:
        return {}

    phase = _phase_from_artifact(artifact_type)
    now = datetime.now(timezone.utc).isoformat()

    workflow_data = {
        f"workflow_{artifact_type}_path": file_path,
        f"workflow_{artifact_type}_updated_at": now,
        "workflow_slug": slug,
        "workflow_phase": phase,
        "workflow_last_transition": now,
    }

    _cortex_cli(
        "session", "update", cortex_session_id,
        "--data", json.dumps(workflow_data),
        "--trigger", f"workflow_{artifact_type}_written",
    )

    return {}


def main():
    hook_input = json.loads(sys.stdin.read())
    result = handle_workflow_file(hook_input)
    print(json.dumps(result))
