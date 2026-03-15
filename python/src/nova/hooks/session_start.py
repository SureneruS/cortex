import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from nova.config import load_config
from nova.lib.frontmatter import read_frontmatter
from nova.lib.state import NovaState
from nova.slack import SlackPoster

NOVA_DIR = Path.home() / ".nova"


def handle_session_start(
    hook_input: dict,
    knowledge_dir: Path | None = None,
    state_file: Path | None = None,
    sessions_dir: Path | None = None,
) -> dict:
    if knowledge_dir is None:
        knowledge_dir = NOVA_DIR / "memory" / "knowledge"
    if state_file is None:
        state_file = NOVA_DIR / "state.json"
    if sessions_dir is None:
        sessions_dir = NOVA_DIR / "sessions"

    session_id = hook_input.get("session_id", "")
    transcript_path = hook_input.get("transcript_path", "")
    cwd = hook_input.get("cwd", "")

    repo_name = Path(cwd).name if cwd else ""

    summaries: list[str] = []
    entries: list[dict[str, str]] = []

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
                    entries.append({"file": f"{subdir}/{md.name}", "title": title})
            except Exception:
                continue

    nova_session_name = os.environ.get("NOVA_SESSION_NAME")

    if session_id and state_file.exists():
        repos = [repo_name] if repo_name else []
        nova_chain_id = os.environ.get("NOVA_CHAIN_ID")
        state = NovaState(state_file)
        state.register_session(
            session_id, repos=repos, transcript_path=transcript_path,
            chain_id=nova_chain_id,
        )

        if nova_session_name and session_id in state.sessions:
            state.sessions[session_id]["tmux_target"] = f"sessions:{nova_session_name}"
            state.sessions[session_id]["tmux_window"] = nova_session_name

        _create_slack_thread(state, session_id, nova_session_name, repo_name)
        state.save()

    if session_id:
        env_file = os.environ.get("CLAUDE_ENV_FILE")
        if env_file:
            with open(env_file, "a") as f:
                f.write(f'export CLAUDE_CODE_SESSION_ID="{session_id}"\n')

        if entries:
            session_dir = sessions_dir / session_id
            session_dir.mkdir(parents=True, exist_ok=True)
            manifest = {
                "session_id": session_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "repo": repo_name,
                "entries": entries,
            }
            with open(session_dir / "injected.json", "w") as f:
                json.dump(manifest, f, indent=2)

    if not summaries:
        return {}

    context = "[Nova] Relevant knowledge from previous sessions:\n\n" + "\n".join(
        summaries
    )
    return _wrap_context(context, "SessionStart")


def _create_slack_thread(
    state: NovaState, session_id: str, session_name: str | None, repo_name: str
):
    if not session_name:
        return

    try:
        config = load_config()
        slack_config = config.get("slack", {})
        bot_token = slack_config.get("bot_token")
        if not bot_token:
            return

        poster = SlackPoster(
            bot_token=bot_token,
            target_user_id=slack_config.get("target_user_id", ""),
        )

        channel = state.slack_config.get("dm_channel")
        if not channel:
            channel = poster.get_dm_channel()
            state.set_slack_config(dm_channel=channel)

        text = f"*{session_name}* started"
        if repo_name:
            text += f" ({repo_name})"

        thread_ts = poster.post_notification(channel=channel, text=text)
        state.set_slack_thread(session_id, thread_ts=thread_ts, channel=channel)
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
