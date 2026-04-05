import json
import os
import subprocess
import sys


def _cortex_cli(*args: str) -> str | None:
    try:
        result = subprocess.run(
            ["cortex", "--json", *args], capture_output=True, text=True, timeout=5
        )
        return result.stdout if result.returncode == 0 else None
    except Exception:
        return None


def handle_user_prompt(hook_input: dict) -> dict:
    cortex_session_id = os.environ.get("CORTEX_SESSION_ID")
    if cortex_session_id:
        _cortex_cli(
            "session", "update", cortex_session_id,
            "--data", json.dumps({"runtime": "working"}),
            "--trigger", "user_prompt",
        )

    return {}


def main():
    hook_input = json.loads(sys.stdin.read())
    result = handle_user_prompt(hook_input)
    print(json.dumps(result))
