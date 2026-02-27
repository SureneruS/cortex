import argparse
import os
import shutil
import sys
import uuid
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
    resume: str | None = None,
    state_file: Path | None = None,
):
    repo_path = Path(repo).resolve()
    window_name = name or repo_path.name

    ensure_session(TMUX_SESSION)

    chain_id = str(uuid.uuid4())
    env_prefix = f"NOVA_SESSION_NAME={window_name} NOVA_CHAIN_ID={chain_id}"

    claude_cmd = "claude"
    if resume:
        claude_cmd += f" --resume {resume}"
    elif agent:
        claude_cmd += f" --agent {agent}"
    claude_cmd += f" --permission-mode {permission_mode}"
    if prompt and not resume:
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
    import subprocess

    # Select the window first, then attach to the session
    subprocess.run(
        ["tmux", "select-window", "-t", f"{TMUX_SESSION}:{name}"],
        capture_output=True,
    )
    os.execlp("tmux", "tmux", "attach-session", "-t", TMUX_SESSION)


def cmd_kill(name: str):
    import subprocess

    result = subprocess.run(
        ["tmux", "kill-window", "-t", f"{TMUX_SESSION}:{name}"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"Session '{name}' not found", file=sys.stderr)
        sys.exit(1)
    print(f"Killed session '{name}'")


def cmd_exchange_install():
    plist_src = Path(__file__).parent.parent.parent.parent / "resources" / "com.nova.exchange.plist"
    plist_dst = Path.home() / "Library" / "LaunchAgents" / "com.nova.exchange.plist"
    nova_dir = Path.home() / ".nova"
    logs_dir = nova_dir / "logs"

    logs_dir.mkdir(parents=True, exist_ok=True)

    if not plist_src.exists():
        print(f"Plist template not found at {plist_src}", file=sys.stderr)
        sys.exit(1)

    nova_bin = shutil.which("nova")
    if not nova_bin:
        print("'nova' not found on PATH", file=sys.stderr)
        sys.exit(1)

    bin_dir = str(Path(nova_bin).parent)
    path_val = f"{bin_dir}:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"

    content = plist_src.read_text()
    content = content.replace("__NOVA_BIN__", nova_bin)
    content = content.replace("__HOME__", str(Path.home()))
    content = content.replace("__PATH__", path_val)
    content = content.replace("__NOVA_DIR__", str(nova_dir))
    plist_dst.write_text(content)

    print(f"Installed plist to {plist_dst}")
    print(f"Run: launchctl load {plist_dst}")


def cmd_rotate(name: str, state_file: Path | None = None):
    from nova.rotation import RotationManager

    if state_file is None:
        state_file = NOVA_DIR / "state.json"

    if not state_file.exists():
        print("No state file found", file=sys.stderr)
        sys.exit(1)

    state = NovaState(state_file)

    target_sid = None
    for sid, session in state.sessions.items():
        if session.get("tmux_window") == name and session.get("status") == "active":
            target_sid = sid
            break

    if not target_sid:
        print(f"No active session found for '{name}'", file=sys.stderr)
        sys.exit(1)

    mgr = RotationManager(state_file=state_file)
    mgr.rotate_now(target_sid)


def cmd_peek(name: str, lines: int = 50):
    import subprocess

    result = subprocess.run(
        ["tmux", "capture-pane", "-t", f"{TMUX_SESSION}:{name}", "-p", "-S", f"-{lines}"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"Session '{name}' not found", file=sys.stderr)
        sys.exit(1)
    print(result.stdout.rstrip())


def cmd_windows():
    import subprocess

    result = subprocess.run(
        ["tmux", "list-windows", "-t", TMUX_SESSION, "-F", "#{window_index}: #{window_name} (#{window_panes} panes)"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print("No tmux session found", file=sys.stderr)
        sys.exit(1)
    print(result.stdout.rstrip())


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
    p_start.add_argument("--resume", "-r", help="Resume an existing session by ID")
    p_start.add_argument(
        "--permission-mode",
        "-p",
        default="acceptEdits",
        help="Permission mode (default: acceptEdits)",
    )

    sub.add_parser("list", aliases=["ls"], help="List active sessions")

    p_attach = sub.add_parser("attach", help="Attach to a session")
    p_attach.add_argument("name", help="Session/window name")

    p_kill = sub.add_parser("kill", help="Kill a session")
    p_kill.add_argument("name", help="Session/window name")

    p_peek = sub.add_parser("peek", help="Peek at a session's output without attaching")
    p_peek.add_argument("name", help="Session/window name")
    p_peek.add_argument("--lines", "-l", type=int, default=50, help="Number of lines (default: 50)")

    p_rotate = sub.add_parser("rotate", help="Rotate (recycle) a session")
    p_rotate.add_argument("name", help="Session/window name")

    sub.add_parser("windows", help="List raw tmux windows")
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
            resume=args.resume,
        )
    elif args.command in ("list", "ls"):
        cmd_list()
    elif args.command == "attach":
        cmd_attach(args.name)
    elif args.command == "peek":
        cmd_peek(args.name, args.lines)
    elif args.command == "kill":
        cmd_kill(args.name)
    elif args.command == "windows":
        cmd_windows()
    elif args.command == "rotate":
        cmd_rotate(args.name)
    elif args.command == "dream":
        cmd_dream()
    elif args.command == "meditate":
        cmd_meditate()
    elif args.command == "exchange":
        if args.exchange_command == "start":
            from nova import exchange

            exchange.run_exchange()
        elif args.exchange_command == "install":
            cmd_exchange_install()
        else:
            print("Usage: nova exchange [start|install]")
