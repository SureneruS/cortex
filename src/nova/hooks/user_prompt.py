import json
import sys
from pathlib import Path

from nova.lib.frontmatter import read_frontmatter
from nova.lib.state import NovaState

NOVA_DIR = Path.home() / ".nova"
MAX_RESULTS = 5

STOP_WORDS = frozenset({
    "the", "a", "an", "is", "are", "was", "were", "be", "been",
    "to", "of", "in", "for", "on", "with", "at", "by", "from",
    "it", "this", "that", "and", "or", "not", "but", "if", "do",
})


def _tokenize(text: str) -> set[str]:
    words = set()
    for word in text.lower().split():
        cleaned = "".join(c for c in word if c.isalnum() or c == "-")
        if len(cleaned) > 2 and cleaned not in STOP_WORDS:
            words.add(cleaned)
    return words


def _score_file(meta: dict, query_tokens: set[str]) -> int:
    searchable = " ".join([
        meta.get("title", ""),
        meta.get("summary", ""),
        " ".join(meta.get("tags", [])),
        " ".join(meta.get("repos", [])),
    ]).lower()
    return sum(1 for token in query_tokens if token in searchable)


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
    prompt_content = hook_input.get("prompt", {}).get("content", "")

    state = NovaState(state_file)
    session = state.sessions.get(session_id, {})
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
            first_line = content.strip().split("\n")[0][:200] if content.strip() else path.stem
            lines.append(f"- **{path.stem}**: {first_line}")

    context = "[Nova] Relevant context for your goal:\n\n" + "\n".join(lines)
    return {"additionalContext": context}


def main():
    hook_input = json.loads(sys.stdin.read())
    result = handle_user_prompt(hook_input)
    print(json.dumps(result))
