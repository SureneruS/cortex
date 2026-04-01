from __future__ import annotations

import abc

import structlog

from cortex.adapters.tmux import TmuxAdapter

log = structlog.get_logger("cortex.daemon")


class DaemonBackend(abc.ABC):
    @abc.abstractmethod
    def start(self, name: str, command: list[str]) -> str: ...

    @abc.abstractmethod
    def stop(self, name: str) -> None: ...

    @abc.abstractmethod
    def status(self, name: str) -> str: ...


class TmuxBackend(DaemonBackend):
    SESSION = "cortex-daemon"

    def __init__(self, tmux: TmuxAdapter | None = None) -> None:
        self._tmux = tmux or TmuxAdapter()

    def _ensure_session(self) -> None:
        self._tmux.ensure_session(self.SESSION)

    def start(self, name: str, command: list[str]) -> str:
        if self.status(name) == "running":
            raise RuntimeError(f"Daemon '{name}' is already running")
        self._ensure_session()
        from pathlib import Path
        log_file = Path.home() / ".cortex" / "logs" / "cortex-daemon.log"
        shell_cmd = " ".join(command) + f" & tail -f {log_file}"
        self._tmux.new_window(
            target_session=self.SESSION,
            window_name=name,
            shell_cmd=shell_cmd,
        )
        return f"{self.SESSION}:{name}"

    def stop(self, name: str) -> None:
        if self.status(name) == "stopped":
            raise RuntimeError(f"Daemon '{name}' is not running")
        self._tmux.kill_window(f"{self.SESSION}:{name}")

    def status(self, name: str) -> str:
        windows = self._tmux.list_windows(self.SESSION)
        return "running" if name in windows else "stopped"
