from __future__ import annotations

import plistlib
import subprocess
from pathlib import Path

import structlog

log = structlog.get_logger("cortex.daemon")

PLIST_LABEL = "com.cortex.daemon"
PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{PLIST_LABEL}.plist"
LOG_DIR = Path.home() / ".cortex" / "logs"


def _find_cortex_bin() -> str:
    """Find the cortex binary path. Prefers the global uv tool install."""
    global_bin = Path.home() / ".local" / "bin" / "cortex"
    if global_bin.exists():
        return str(global_bin)
    result = subprocess.run(["which", "cortex"], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError("'cortex' not found on PATH. Install with: uv tool install --editable . --force")
    return result.stdout.strip()


def _build_plist(cortex_bin: str) -> dict:
    """Build the launchd plist configuration."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    return {
        "Label": PLIST_LABEL,
        "ProgramArguments": [cortex_bin, "daemon", "run"],
        "RunAtLoad": True,
        "KeepAlive": True,
        "StandardOutPath": str(LOG_DIR / "cortex-daemon-stdout.log"),
        "StandardErrorPath": str(LOG_DIR / "cortex-daemon-stderr.log"),
        "EnvironmentVariables": {
            "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin",
        },
    }


def install() -> str:
    cortex_bin = _find_cortex_bin()
    plist = _build_plist(cortex_bin)

    PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(PLIST_PATH, "wb") as f:
        plistlib.dump(plist, f)

    return str(PLIST_PATH)


def start() -> None:
    if status() == "running":
        raise RuntimeError("Daemon is already running")

    install()
    result = subprocess.run(
        ["launchctl", "load", str(PLIST_PATH)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"launchctl load failed: {result.stderr.strip()}")


def stop() -> None:
    if status() == "stopped":
        raise RuntimeError("Daemon is not running")

    result = subprocess.run(
        ["launchctl", "unload", str(PLIST_PATH)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"launchctl unload failed: {result.stderr.strip()}")


def status() -> str:
    result = subprocess.run(
        ["launchctl", "list", PLIST_LABEL],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return "stopped"

    # Parse launchctl list output for PID
    for line in result.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) >= 3 and parts[2] == PLIST_LABEL:
            pid = parts[0].strip()
            if pid == "-":
                return "stopped"
            return "running"

    # launchctl list succeeded (found label) — check if process is alive
    return "running"


def uninstall() -> None:
    """Stop daemon and remove the plist file."""
    if status() == "running":
        stop()
    if PLIST_PATH.exists():
        PLIST_PATH.unlink()
