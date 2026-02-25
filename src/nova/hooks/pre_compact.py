from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from nova.lib.state import NovaState

NOVA_DIR = Path.home() / ".nova"
MAX_RECENT_MESSAGES = 50


def _extract_recent_content(transcript_path: Path) -> str:
    try:
        all_lines = transcript_path.read_text().splitlines()
    except Exception:
        return ""

    messages = []
    for line in all_lines:
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue

        msg = entry.get("message", {})
        role = msg.get("role")
        if role not in ("assistant", "user"):
            continue

        content = msg.get("content", "")
        if isinstance(content, list):
            text_parts = [
                item.get("text", "")
                for item in content
                if isinstance(item, dict) and item.get("type") == "text"
            ]
            content = "\n".join(text_parts)
        if isinstance(content, str) and content.strip():
            messages.append(f"[{role}] {content[:500]}")

    return "\n\n".join(messages[-MAX_RECENT_MESSAGES:])


def handle_pre_compact(
    hook_input: dict,
    state_file: Path | None = None,
    captures_dir: Path | None = None,
) -> dict:
    if state_file is None:
        state_file = NOVA_DIR / "state.json"
    if captures_dir is None:
        captures_dir = NOVA_DIR / "memory" / "captures"

    session_id = hook_input.get("session_id", "")
    transcript_path = hook_input.get("transcript_path", "")

    if not session_id or not state_file.exists():
        return {}

    try:
        state = NovaState(state_file)
    except Exception:
        return {}

    session = state.sessions.get(session_id)
    if not session:
        return {}

    if transcript_path:
        content = _extract_recent_content(Path(transcript_path))
    else:
        content = ""

    if content:
        captures_dir.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc)
        filename = f"{now.strftime('%Y-%m-%d-%H%M%S')}-{session_id[:8]}-compact.md"
        repos = session.get("repos", [])
        repo_list = ", ".join(repos) if repos else "unknown"

        capture = (
            f"---\n"
            f"session: {session_id}\n"
            f"repos: [{repo_list}]\n"
            f"transcript: {transcript_path}\n"
            f"captured_at: {now.isoformat()}\n"
            f"schema_version: 1\n"
            f"trigger: pre_compact\n"
            f"---\n\n"
            f"### Pre-compaction transcript snapshot\n\n"
            f"Recent conversation content:\n\n{content}\n"
        )
        (captures_dir / filename).write_text(capture)

    state.increment_compaction(session_id)
    state.save()

    return {}


def main():
    log_file = NOVA_DIR / "logs" / "pre_compact.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)

    raw = sys.stdin.read()
    try:
        hook_input = json.loads(raw)
    except Exception as e:
        with log_file.open("a") as f:
            f.write(f"PARSE ERROR: {e}\n")
        print(json.dumps({}))
        return

    with log_file.open("a") as f:
        f.write(f"CALLED: session={hook_input.get('session_id', '?')}\n")

    try:
        result = handle_pre_compact(hook_input)
    except Exception:
        import traceback

        with log_file.open("a") as f:
            f.write(f"ERROR: {traceback.format_exc()}\n")
        print(json.dumps({}))
        return

    print(json.dumps(result))
