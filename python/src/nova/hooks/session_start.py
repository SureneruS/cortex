import json
import os
import subprocess
import sys
from pathlib import Path

CORTEX_KNOWLEDGE_DIR = Path.home() / "cortex" / "knowledge"


def _cortex_cli(*args: str) -> str | None:
    try:
        result = subprocess.run(
            ["cortex", "--json", *args], capture_output=True, text=True, timeout=5
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


def _extract_summary(path: Path) -> str | None:
    """Extract the summary field from YAML frontmatter."""
    try:
        text = path.read_text()
    except (FileNotFoundError, PermissionError):
        return None

    if not text.startswith("---"):
        return None

    end = text.find("---", 3)
    if end == -1:
        return None

    frontmatter = text[3:end]
    for line in frontmatter.splitlines():
        line = line.strip()
        if line.startswith("summary:"):
            value = line[len("summary:"):].strip()
            return value.strip("\"'")
    return None


def _load_knowledge_context(repo_name: str) -> str | None:
    """Load relevant knowledge summaries for injection."""
    if not CORTEX_KNOWLEDGE_DIR.is_dir():
        return None

    entries: list[str] = []

    # Global knowledge
    global_dir = CORTEX_KNOWLEDGE_DIR / "global"
    if global_dir.is_dir():
        for f in sorted(global_dir.glob("*.md")):
            summary = _extract_summary(f)
            if summary:
                entries.append(f"- **{f.stem}**: {summary}")

    # Repo-specific knowledge
    if repo_name:
        repo_dir = CORTEX_KNOWLEDGE_DIR / f"repo-{repo_name}"
        if repo_dir.is_dir():
            for f in sorted(repo_dir.glob("*.md")):
                summary = _extract_summary(f)
                if summary:
                    entries.append(f"- **{f.stem}**: {summary}")

    if not entries:
        return None

    return "# Cortex Knowledge\n\n" + "\n".join(entries)


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
            needs_reactivation = existing_data.get("status") in ("paused", "blocked", "completed", "closed")

            if needs_reactivation:
                _cortex_cli(
                    "session", "update", cortex_session_id,
                    "--data", json.dumps({"status": "active"}),
                    "--trigger", "session_reactivate",
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
        register_output = _cortex_cli(
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

        # Write CORTEX_SESSION_ID/NAME so cortex CLI commands work within this session
        env_file = os.environ.get("CLAUDE_ENV_FILE")
        if register_output and env_file:
            try:
                doc = json.loads(register_output)
                with open(env_file, "a") as f:
                    f.write(f"CORTEX_SESSION_ID={doc['_id']}\n")
                    f.write(f"CORTEX_SESSION_NAME={doc.get('name', repo_name or 'manual')}\n")
            except (json.JSONDecodeError, KeyError, OSError):
                pass

    result: dict = {}
    context_parts: list[str] = []

    workflow_ctx = _load_workflow_context()
    if workflow_ctx:
        context_parts.append(workflow_ctx)

    knowledge_ctx = _load_knowledge_context(repo_name)
    if knowledge_ctx:
        context_parts.append(knowledge_ctx)

    if context_parts:
        result["hookSpecificOutput"] = {
            "hookEventName": "SessionStart",
            "additionalContext": "\n\n".join(context_parts),
        }
    return result


def main():
    hook_input = json.loads(sys.stdin.read())
    result = handle_session_start(hook_input)
    print(json.dumps(result))
