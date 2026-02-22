import json
import sys
from pathlib import Path

from nova.lib.frontmatter import read_frontmatter
from nova.lib.state import NovaState

NOVA_DIR = Path.home() / ".nova"


def handle_session_start(
    hook_input: dict,
    knowledge_dir: Path | None = None,
    state_file: Path | None = None,
) -> dict:
    if knowledge_dir is None:
        knowledge_dir = NOVA_DIR / "memory" / "knowledge"
    if state_file is None:
        state_file = NOVA_DIR / "state.json"

    session_id = hook_input.get("session_id", "")
    transcript_path = hook_input.get("transcript_path", "")
    cwd = hook_input.get("cwd", "")

    repo_name = Path(cwd).name if cwd else ""

    summaries: list[str] = []

    for subdir in [f"repo-{repo_name}", "global"]:
        d = knowledge_dir / subdir
        if not d.is_dir():
            continue
        for md in sorted(d.glob("*.md")):
            try:
                meta, _ = read_frontmatter(md)
                title = meta.get("title", md.stem)
                summary = meta.get("summary", "")
                if summary:
                    summaries.append(f"- **{title}**: {summary}")
            except Exception:
                continue

    if session_id and state_file.exists():
        repos = [repo_name] if repo_name else []
        state = NovaState(state_file)
        state.register_session(session_id, repos=repos, transcript_path=transcript_path)
        state.save()

    if not summaries:
        return {}

    context = "[Nova] Relevant knowledge from previous sessions:\n\n" + "\n".join(
        summaries
    )
    return {"additionalContext": context}


def main():
    hook_input = json.loads(sys.stdin.read())
    result = handle_session_start(hook_input)
    print(json.dumps(result))
