from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from nova.lib.state import CompactCursor, NovaState

NOVA_DIR = Path.home() / ".nova"


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
    state_file: Path | None = None,
    queue_dir: Path | None = None,
) -> dict:
    if state_file is None:
        state_file = NOVA_DIR / "state.json"
    if queue_dir is None:
        queue_dir = NOVA_DIR / "memory" / "queue"

    session_id = hook_input.get("session_id", "")
    transcript_path = hook_input.get("transcript_path", "")

    # Update Cortex registry
    cortex_session_id = os.environ.get("CORTEX_SESSION_ID")
    if cortex_session_id:
        _cortex_cli(
            "session", "update", cortex_session_id,
            "--data", json.dumps({"last_compaction": datetime.now(timezone.utc).isoformat()}),
            "--trigger", "pre_compact",
        )

    if not session_id or not state_file.exists():
        return {}

    try:
        state = NovaState(state_file)
    except Exception:
        return {}

    session = state.sessions.get(session_id)
    if not session:
        return {}

    cursor = session.get("compact_cursor", {"line": 0, "byte": 0, "time": ""})
    from_line = cursor["line"]

    if transcript_path:
        to_line, to_byte, from_time, to_time = _scan_transcript_bounds(
            Path(transcript_path), from_line
        )
    else:
        to_line, to_byte, from_time, to_time = from_line, cursor["byte"], "", ""

    if to_line > from_line:
        queue_dir.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc)
        job = {
            "session_id": session_id,
            "transcript_path": transcript_path,
            "from_line": from_line,
            "to_line": to_line,
            "from_byte": cursor["byte"],
            "to_byte": to_byte,
            "from_time": cursor["time"] or from_time,
            "to_time": to_time,
            "repos": session.get("repos", []),
            "queued_at": now.isoformat(),
        }
        filename = f"{now.strftime('%Y%m%d-%H%M%S-%f')}-{session_id[:8]}.json"
        (queue_dir / filename).write_text(json.dumps(job, indent=2) + "\n")

        new_cursor = CompactCursor(line=to_line, byte=to_byte, time=to_time)
        state.set_compact_cursor(session_id, new_cursor)

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
