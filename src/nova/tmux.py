import subprocess

TMUX_SESSION = "sessions"


def ensure_session(session_name: str = TMUX_SESSION) -> None:
    result = subprocess.run(
        ["tmux", "has-session", "-t", session_name],
        capture_output=True,
    )
    if result.returncode != 0:
        subprocess.run(
            ["tmux", "new-session", "-d", "-s", session_name],
            check=True,
        )


def create_window(session_name: str, window_name: str, command: str) -> None:
    subprocess.run(
        ["tmux", "new-window", "-t", session_name, "-n", window_name, command],
        check=True,
    )


def send_keys(target: str, text: str) -> None:
    # Send text literally (-l prevents tmux key name interpretation)
    subprocess.run(
        ["tmux", "send-keys", "-t", target, "-l", text],
        check=True,
    )
    # Then press Enter
    subprocess.run(
        ["tmux", "send-keys", "-t", target, "Enter"],
        check=True,
    )


def is_client_attached(target: str) -> bool:
    result = subprocess.run(
        ["tmux", "list-clients", "-t", target, "-F", "#{client_tty}"],
        capture_output=True,
        text=True,
    )
    return bool(result.stdout.strip())


def has_window(session_name: str, window_name: str) -> bool:
    result = subprocess.run(
        ["tmux", "has-session", "-t", f"{session_name}:{window_name}"],
        capture_output=True,
    )
    return result.returncode == 0


def list_windows(session_name: str = TMUX_SESSION) -> list[str]:
    result = subprocess.run(
        ["tmux", "list-windows", "-t", session_name, "-F", "#{window_name}"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []
    return [w for w in result.stdout.strip().split("\n") if w]
