from __future__ import annotations

import abc
import logging
import subprocess

log = logging.getLogger("cortex.daemon")


class DaemonBackend(abc.ABC):
    @abc.abstractmethod
    def start(self, name: str, command: list[str]) -> str:
        """Start a daemon process. Returns an identifier."""

    @abc.abstractmethod
    def stop(self, name: str) -> None:
        """Stop a daemon process."""

    @abc.abstractmethod
    def status(self, name: str) -> str:
        """Get daemon status: 'running' or 'stopped'."""


class TmuxBackend(DaemonBackend):
    SESSION = "cortex-daemon"

    def _ensure_session(self) -> None:
        result = subprocess.run(
            ["tmux", "has-session", "-t", self.SESSION],
            capture_output=True,
        )
        if result.returncode != 0:
            subprocess.run(
                ["tmux", "new-session", "-d", "-s", self.SESSION, "-n", "init"],
                capture_output=True,
                check=True,
            )

    def start(self, name: str, command: list[str]) -> str:
        if self.status(name) == "running":
            raise RuntimeError(f"Daemon '{name}' is already running")
        self._ensure_session()
        subprocess.run(
            ["tmux", "new-window", "-t", self.SESSION, "-n", name, *command],
            capture_output=True,
            check=True,
        )
        return f"{self.SESSION}:{name}"

    def stop(self, name: str) -> None:
        if self.status(name) == "stopped":
            raise RuntimeError(f"Daemon '{name}' is not running")
        subprocess.run(
            ["tmux", "kill-window", "-t", f"{self.SESSION}:{name}"],
            capture_output=True,
            check=True,
        )

    def status(self, name: str) -> str:
        result = subprocess.run(
            ["tmux", "list-windows", "-t", self.SESSION, "-F", "#{window_name}"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return "stopped"
        windows = result.stdout.strip().split("\n")
        return "running" if name in windows else "stopped"
