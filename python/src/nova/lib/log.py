from __future__ import annotations

import sys
from datetime import datetime


_COLORS = {
    "exchange": "\033[36m",   # cyan
    "watcher": "\033[35m",    # magenta
    "rotation": "\033[33m",   # yellow
    "dream": "\033[34m",      # blue
}
_RESET = "\033[0m"
_DIM = "\033[2m"
_BOLD = "\033[1m"
_RED = "\033[31m"


def nova_log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")

    tag = ""
    color = ""
    body = msg
    if msg.startswith("[") and "]" in msg:
        end = msg.index("]")
        tag = msg[1:end]
        body = msg[end + 1:].lstrip()
        color = _COLORS.get(tag, "")

    if "ERROR" in body:
        line = f"{_DIM}{ts}{_RESET} {color}{_BOLD}[{tag}]{_RESET} {_RED}{body}{_RESET}"
    elif tag:
        line = f"{_DIM}{ts}{_RESET} {color}[{tag}]{_RESET} {body}"
    else:
        line = f"{_DIM}{ts}{_RESET} {msg}"

    print(line, flush=True)
