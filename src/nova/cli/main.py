import argparse
import os
from pathlib import Path

from nova.lib.state import NovaState
from nova.tmux import ensure_session, create_window, list_windows

NOVA_DIR = Path.home() / ".nova"
TMUX_SESSION = "sessions"


def cmd_start(
    repo: str,
    name: str | None = None,
    agent: str | None = None,
    permission_mode: str = "acceptEdits",
    prompt: str | None = None,
    state_file: Path | None = None,
):
    repo_path = Path(repo).resolve()
    window_name = name or repo_path.name

    ensure_session(TMUX_SESSION)

    env_prefix = f"NOVA_SESSION_NAME={window_name}"

    claude_cmd = "claude"
    if agent:
        claude_cmd += f" --agent {agent}"
    claude_cmd += f" --permission-mode {permission_mode}"
    if prompt:
        claude_cmd += f' "{prompt}"'

    full_command = f"cd {repo_path} && export {env_prefix} && {claude_cmd}"

    create_window(
        session_name=TMUX_SESSION,
        window_name=window_name,
        command=full_command,
    )

    print(f"Started session '{window_name}' in tmux")


def cmd_list(state_file: Path | None = None):
    if state_file is None:
        state_file = NOVA_DIR / "state.json"

    windows = list_windows(TMUX_SESSION)

    session_map = {}
    if state_file.exists():
        try:
            state = NovaState(state_file)
            for data in state.sessions.values():
                w = data.get("tmux_window")
                if w:
                    session_map[w] = data
        except Exception:
            pass

    print(f"{'NAME':<25} {'REPO':<25} {'SLACK':<10}")
    print("-" * 60)
    for w in windows:
        info = session_map.get(w, {})
        repos = info.get("repos", [])
        repo_str = repos[0] if repos else "—"
        slack = "threaded" if info.get("slack_thread_ts") else "—"
        print(f"{w:<25} {repo_str:<25} {slack:<10}")

    if not windows:
        print("No active sessions")


def cmd_attach(name: str):
    os.execlp("tmux", "tmux", "select-window", "-t", f"{TMUX_SESSION}:{name}")


def cmd_dream():
    os.execlp("claude", "claude", "--agent", "dream")


def cmd_meditate():
    os.execlp("claude", "claude", "--agent", "meditate")


def main():
    parser = argparse.ArgumentParser(prog="nova", description="Nova session coordinator")
    sub = parser.add_subparsers(dest="command", required=True)

    p_start = sub.add_parser("start", help="Start a Claude Code session in tmux")
    p_start.add_argument("repo", help="Path to repository")
    p_start.add_argument("prompt", nargs="?", help="Initial prompt")
    p_start.add_argument("--name", "-n", help="Custom window name")
    p_start.add_argument("--agent", "-a", help="Agent config name")
    p_start.add_argument(
        "--permission-mode",
        "-p",
        default="acceptEdits",
        help="Permission mode (default: acceptEdits)",
    )

    sub.add_parser("list", aliases=["ls"], help="List active sessions")

    p_attach = sub.add_parser("attach", help="Attach to a session")
    p_attach.add_argument("name", help="Session/window name")

    sub.add_parser("dream", help="Run dream agent")
    sub.add_parser("meditate", help="Run meditate agent")

    p_exchange = sub.add_parser("exchange", help="Manage the exchange daemon")
    ex_sub = p_exchange.add_subparsers(dest="exchange_command")
    ex_sub.add_parser("start", help="Start exchange (foreground)")
    ex_sub.add_parser("install", help="Install launchctl plist")

    args = parser.parse_args()

    if args.command == "start":
        cmd_start(
            repo=args.repo,
            name=args.name,
            agent=args.agent,
            permission_mode=args.permission_mode,
            prompt=args.prompt,
        )
    elif args.command in ("list", "ls"):
        cmd_list()
    elif args.command == "attach":
        cmd_attach(args.name)
    elif args.command == "dream":
        cmd_dream()
    elif args.command == "meditate":
        cmd_meditate()
    elif args.command == "exchange":
        if args.exchange_command == "start":
            print("Exchange not yet implemented")
        elif args.exchange_command == "install":
            print("Exchange not yet implemented")
        else:
            print("Usage: nova exchange [start|install]")
