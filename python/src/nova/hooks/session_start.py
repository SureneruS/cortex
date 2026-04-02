import json
import os
import subprocess
import sys
from pathlib import Path

NOVA_DIR = Path.home() / ".nova"


def _cortex_cli(*args: str) -> str | None:
    try:
        result = subprocess.run(
            ["cortex", *args], capture_output=True, text=True, timeout=5
        )
        return result.stdout if result.returncode == 0 else None
    except Exception:
        return None


def _load_workflow_context() -> str | None:
    """Load workflow context for injection into all sessions."""
    # Find the workflow-context.md relative to the plugin
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT", "")
    if plugin_root:
        ctx_path = Path(plugin_root) / "hooks" / "workflow-context.md"
    else:
        # Fallback: search from cortex repo
        ctx_path = Path(__file__).parents[4] / "plugin" / "hooks" / "workflow-context.md"

    try:
        return ctx_path.read_text()
    except (FileNotFoundError, PermissionError):
        return None


def handle_session_start(hook_input: dict) -> dict:
    session_id = hook_input.get("session_id", "")
    transcript_path = hook_input.get("transcript_path", "")
    cwd = hook_input.get("cwd", "")
    repo_name = Path(cwd).name if cwd else ""

    cortex_session_id = os.environ.get("CORTEX_SESSION_ID")

    cc_version = None
    try:
        vr = subprocess.run(["claude", "--version"], capture_output=True, text=True, timeout=3)
        if vr.returncode == 0:
            cc_version = vr.stdout.strip()
    except Exception:
        pass

    if cortex_session_id and session_id:
        existing = _cortex_cli("session", "get", cortex_session_id)
        existing_data = None
        if existing:
            try:
                existing_data = json.loads(existing)
            except (json.JSONDecodeError, TypeError):
                pass

        if existing_data:
            is_terminal = existing_data.get("status") in ("completed", "dead")

            if is_terminal:
                # Reactivate — /clear fired after session was marked terminal
                _cortex_cli(
                    "session", "update", cortex_session_id,
                    "--data", json.dumps({"status": "active"}),
                    "--trigger", "clear_reactivate",
                )

            # Link new CC session (appends to cc_sessions array)
            extra: dict = {"transcript_path": transcript_path}
            if cc_version:
                extra["cc_version"] = cc_version
            _cortex_cli(
                "session", "link-cc", cortex_session_id, session_id,
                "--data", json.dumps(extra),
            )

            # Update top-level fields
            update_data: dict = {"transcript_path": transcript_path}
            if cc_version:
                update_data["cc_version"] = cc_version
            if not existing_data.get("repos"):
                update_data["repos"] = [repo_name] if repo_name else []
            _cortex_cli(
                "session", "update", cortex_session_id,
                "--data", json.dumps(update_data),
                "--trigger", "session_start_hook",
            )
        else:
            # Cortex session not found at all — should not happen, but register
            _cortex_cli(
                "session", "register",
                "--id", cortex_session_id,
                "--data", json.dumps({
                    "cc_session_id": session_id,
                    "name": repo_name or "orphan",
                    "role": os.environ.get("CORTEX_SESSION_ROLE", "worker"),
                    "spawned_by": "hook",
                    "transcript_path": transcript_path,
                    "repos": [repo_name] if repo_name else [],
                }),
            )
    elif session_id:
        # Manual session: register new entry in Cortex registry
        _cortex_cli(
            "session", "register",
            "--data", json.dumps({
                "cc_session_id": session_id,
                "name": repo_name or "manual",
                "role": os.environ.get("CORTEX_SESSION_ROLE", "manual"),
                "spawned_by": "manual",
                "transcript_path": transcript_path,
                "repos": [repo_name] if repo_name else [],
            }),
        )

    # Also write to Nova state.json for backward compatibility
    _legacy_nova_register(session_id, transcript_path, repo_name)

    result: dict = {}
    workflow_ctx = _load_workflow_context()
    if workflow_ctx:
        result["hookSpecificOutput"] = {
            "hookEventName": "SessionStart",
            "additionalContext": workflow_ctx,
        }
    return result


def _legacy_nova_register(session_id: str, transcript_path: str, repo_name: str) -> None:
    """Write to ~/.nova/state.json for backward compat (until fully migrated)."""
    try:
        from nova.lib.state import NovaState

        state_file = NOVA_DIR / "state.json"
        if not state_file.exists():
            return
        state = NovaState(state_file)
        repos = [repo_name] if repo_name else []
        state.register_session(session_id, repos=repos, transcript_path=transcript_path)
        state.save()
    except Exception:
        pass


def main():
    hook_input = json.loads(sys.stdin.read())
    result = handle_session_start(hook_input)
    print(json.dumps(result))
