import json
import os
import subprocess
import sys
from datetime import datetime, timezone
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


def _get_knowledge_summaries(cwd: str) -> list[str]:
    knowledge_dir = NOVA_DIR / "memory" / "knowledge"
    repo_name = Path(cwd).name if cwd else ""
    summaries: list[str] = []

    for subdir in [f"repo-{repo_name}", "global"]:
        d = knowledge_dir / subdir
        if not d.is_dir():
            continue
        for md in sorted(d.glob("*.md")):
            try:
                from nova.lib.frontmatter import read_frontmatter

                meta, _ = read_frontmatter(md)
                title = meta.get("title", md.stem)
                summary = meta.get("summary", "")
                if summary:
                    summaries.append(f"- **{title}**: {summary}")
            except Exception:
                continue
    return summaries


def handle_session_start(hook_input: dict) -> dict:
    session_id = hook_input.get("session_id", "")
    transcript_path = hook_input.get("transcript_path", "")
    cwd = hook_input.get("cwd", "")
    repo_name = Path(cwd).name if cwd else ""

    cortex_session_id = os.environ.get("CORTEX_SESSION_ID")

    if cortex_session_id and session_id:
        # Spawned session: link CC UUID to existing Cortex registry entry
        # Don't overwrite repos if already set at spawn time (--repo flag)
        update_data: dict = {
            "cc_session_id": session_id,
            "transcript_path": transcript_path,
        }
        existing = _cortex_cli("session", "get", cortex_session_id)
        has_repos = False
        if existing:
            try:
                existing_data = json.loads(existing)
                has_repos = bool(existing_data.get("repos"))
            except (json.JSONDecodeError, TypeError):
                pass
        if not has_repos:
            update_data["repos"] = [repo_name] if repo_name else []
        _cortex_cli(
            "session", "update", cortex_session_id,
            "--data", json.dumps(update_data),
            "--trigger", "session_start_hook",
        )
    elif session_id:
        # Manual session: register new entry in Cortex registry
        _cortex_cli(
            "session", "register",
            "--data", json.dumps({
                "cc_session_id": session_id,
                "name": repo_name or "manual",
                "role": os.environ.get("CORTEX_SESSION_ROLE", "control"),
                "spawned_by": "manual",
                "transcript_path": transcript_path,
                "repos": [repo_name] if repo_name else [],
            }),
        )

    # Also write to Nova state.json for backward compatibility
    _legacy_nova_register(session_id, transcript_path, repo_name)

    # Inject knowledge context
    summaries = _get_knowledge_summaries(cwd)
    if not summaries:
        return {}

    context = "[Cortex] Relevant knowledge from previous sessions:\n\n" + "\n".join(
        summaries
    )
    return _wrap_context(context, "SessionStart")


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


def _wrap_context(context: str, event_name: str) -> dict:
    return {
        "additionalContext": context,
        "hookSpecificOutput": {
            "hookEventName": event_name,
            "additionalContext": context,
        },
    }


def main():
    hook_input = json.loads(sys.stdin.read())
    result = handle_session_start(hook_input)
    print(json.dumps(result))
