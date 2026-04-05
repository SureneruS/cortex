from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

CORTEX_DIR = Path.home() / "cortex"


def _cortex_cli(*args: str) -> str | None:
    try:
        result = subprocess.run(
            ["cortex", "--json", *args], capture_output=True, text=True, timeout=5
        )
        return result.stdout if result.returncode == 0 else None
    except Exception:
        return None


def _scan_transcript_bounds(
    path: Path, from_line: int
) -> tuple[int, int, str, str]:
    to_line = from_line
    to_byte = 0
    from_time = ""
    to_time = ""

    try:
        with path.open("rb") as f:
            for line_num, raw_line in enumerate(f):
                to_byte += len(raw_line)
                if line_num < from_line:
                    continue
                to_line = line_num + 1
                try:
                    entry = json.loads(raw_line)
                except (json.JSONDecodeError, ValueError):
                    continue
                ts = entry.get("timestamp", "")
                if ts:
                    if not from_time:
                        from_time = ts
                    to_time = ts
    except Exception:
        pass

    return to_line, to_byte, from_time, to_time


def handle_pre_compact(
    hook_input: dict,
    queue_dir: Path | None = None,
) -> dict:
    if queue_dir is None:
        queue_dir = CORTEX_DIR / "captures"

    session_id = hook_input.get("session_id", "")
    transcript_path = hook_input.get("transcript_path", "")
    compact_summary = hook_input.get("summary", "")

    # Update Cortex registry
    cortex_session_id = os.environ.get("CORTEX_SESSION_ID")
    if cortex_session_id:
        _cortex_cli(
            "session", "update", cortex_session_id,
            "--data", json.dumps({"last_compaction": datetime.now(timezone.utc).isoformat()}),
            "--trigger", "pre_compact",
        )

    if not session_id:
        return {}

    # Write compact summary as a capture for dream to process
    if compact_summary:
        queue_dir.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc)
        filename = f"{now.strftime('%Y-%m-%d-%H%M%S')}-{session_id[:8]}-compact.md"
        content = f"""---
source: compact_summary
session_id: {session_id}
transcript_path: {transcript_path}
captured_at: {now.isoformat()}
---

{compact_summary}
"""
        (queue_dir / filename).write_text(content)
    elif transcript_path:
        # No summary provided — scan transcript and write range metadata for dream
        from_line = 0
        to_line, to_byte, from_time, to_time = _scan_transcript_bounds(
            Path(transcript_path), from_line
        )
        if to_line > from_line:
            queue_dir.mkdir(parents=True, exist_ok=True)
            now = datetime.now(timezone.utc)
            job = {
                "source": "transcript_range",
                "session_id": session_id,
                "transcript_path": transcript_path,
                "from_line": from_line,
                "to_line": to_line,
                "from_time": from_time,
                "to_time": to_time,
                "queued_at": now.isoformat(),
            }
            filename = f"{now.strftime('%Y-%m-%d-%H%M%S')}-{session_id[:8]}-range.json"
            (queue_dir / filename).write_text(json.dumps(job, indent=2) + "\n")

    return {}


def main():
    hook_input = json.loads(sys.stdin.read())
    result = handle_pre_compact(hook_input)
    print(json.dumps(result))
