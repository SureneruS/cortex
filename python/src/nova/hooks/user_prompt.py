import json
import os
import subprocess
import sys
from pathlib import Path

from nova.lib.frontmatter import read_frontmatter
from nova.lib.state import NovaState

NOVA_DIR = Path.home() / ".nova"
MAX_RESULTS = 5

CONFIRMATION_PHRASES = [
    "that worked",
    "that fixed",
    "it works",
    "it's fixed",
    "its fixed",
    "fix works",
    "working now",
    "fixed it",
    "solved it",
    "got it working",
    "nailed it",
    "that did it",
    "problem solved",
    "all good now",
    "that was it",
    "works now",
    "issue resolved",
]

STOP_WORDS = frozenset(
    {
        "the",
        "a",
        "an",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "to",
        "of",
        "in",
        "for",
        "on",
        "with",
        "at",
        "by",
        "from",
        "it",
        "this",
        "that",
        "and",
        "or",
        "not",
        "but",
        "if",
        "do",
    }
)


def _cortex_cli(*args: str) -> str | None:
    try:
        result = subprocess.run(
            ["cortex", *args], capture_output=True, text=True, timeout=5
        )
        return result.stdout if result.returncode == 0 else None
    except Exception:
        return None


def _tokenize(text: str) -> set[str]:
    words = set()
    for word in text.lower().split():
        cleaned = "".join(c for c in word if c.isalnum() or c == "-")
        if len(cleaned) > 2 and cleaned not in STOP_WORDS:
            words.add(cleaned)
    return words


def _score_file(meta: dict, query_tokens: set[str]) -> int:
    searchable = " ".join(
        [
            meta.get("title", ""),
            meta.get("summary", ""),
            " ".join(meta.get("tags", [])),
            " ".join(meta.get("repos", [])),
        ]
    ).lower()
    return sum(1 for token in query_tokens if token in searchable)


def _check_confirmation(prompt: str) -> str | None:
    lower = prompt.lower()
    for phrase in CONFIRMATION_PHRASES:
        if phrase in lower:
            return phrase
    return None


def handle_user_prompt(
    hook_input: dict,
    nova_dir: Path | None = None,
    state_file: Path | None = None,
) -> dict:
    if nova_dir is None:
        nova_dir = NOVA_DIR
    if state_file is None:
        state_file = nova_dir / "state.json"

    session_id = hook_input.get("session_id", "")
    prompt_content = hook_input.get("prompt", "")

    # Update Cortex registry with last_active_at
    cortex_session_id = os.environ.get("CORTEX_SESSION_ID")
    if cortex_session_id:
        _cortex_cli(
            "session", "update", cortex_session_id,
            "--data", json.dumps({"runtime": "working"}),
            "--trigger", "user_prompt",
        )

    if not state_file.exists():
        return {}
    state = NovaState(state_file)
    session = state.sessions.get(session_id, {})

    # Check for confirmation phrases on ALL prompts (not just first)
    if prompt_content and session.get("memory_injected", False):
        match = _check_confirmation(prompt_content)
        if match:
            context = "[Cortex] Sounds like you resolved something — consider running /memorize to capture what you learned."
            return _wrap_context(context, "UserPromptSubmit")
        return {}

    if session.get("memory_injected", False):
        return {}

    if not prompt_content:
        return {}

    query_tokens = _tokenize(prompt_content)
    if not query_tokens:
        return {}

    scored: list[tuple[int, dict, str, Path]] = []

    knowledge_dir = nova_dir / "memory" / "knowledge"
    if knowledge_dir.is_dir():
        for md in knowledge_dir.rglob("*.md"):
            try:
                meta, content = read_frontmatter(md)
                score = _score_file(meta, query_tokens)
                if score > 0:
                    scored.append((score, meta, content, md))
            except Exception:
                continue

    captures_dir = nova_dir / "memory" / "captures"
    if captures_dir.is_dir():
        for md in sorted(captures_dir.glob("*.md")):
            try:
                meta, content = read_frontmatter(md)
                score = _score_file(meta, query_tokens)
                if score > 0:
                    scored.append((score, meta, content, md))
            except Exception:
                continue

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:MAX_RESULTS]

    if session_id:
        state.mark_injected(session_id, goal=prompt_content)
        state.save()

    if not top:
        return {}

    lines = []
    for _score, meta, content, path in top:
        title = meta.get("title", path.stem)
        summary = meta.get("summary", "")
        if summary:
            lines.append(f"- **{title}**: {summary}")
        else:
            first_line = (
                content.strip().split("\n")[0][:200] if content.strip() else path.stem
            )
            lines.append(f"- **{path.stem}**: {first_line}")

    context = "[Cortex] Relevant context for your goal:\n\n" + "\n".join(lines)
    return _wrap_context(context, "UserPromptSubmit")


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
    result = handle_user_prompt(hook_input)
    print(json.dumps(result))
