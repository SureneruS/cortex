from __future__ import annotations

import os
import subprocess
import tempfile
import time

import structlog

log = structlog.get_logger("cortex.tmux")


class TmuxAdapter:
    """Wraps all tmux subprocess interactions.

    Core methods implement the TerminalAdapter protocol.
    Additional methods provide tmux-specific spatial operations.
    """

    # ── Core TerminalAdapter operations ──────────────────────

    def pane_exists(self, pane_id: str) -> bool:
        pane_id = str(pane_id)
        if not pane_id.startswith("%"):
            return False
        result = self._run("capture-pane", "-t", pane_id, "-p")
        return result.returncode == 0

    def create_pane(
        self,
        cwd: str,
        shell_cmd: str,
        *,
        target_session: str | None = None,
    ) -> str | None:
        args = ["new-window", "-d", "-P", "-F", "#{pane_id}", "-c", cwd]
        if target_session:
            args.extend(["-t", target_session])
        args.extend(["fish", "-c", shell_cmd])
        result = self._run(*args)
        if result.returncode != 0:
            log.error("create_pane failed", stderr=result.stderr.strip())
            return None
        return result.stdout.strip() or None

    def destroy_pane(self, pane_id: str) -> bool:
        result = self._run("kill-pane", "-t", str(pane_id))
        return result.returncode == 0

    def capture_output(self, pane_id: str, lines: int = 50) -> str | None:
        result = self._run("capture-pane", "-t", str(pane_id), "-p", "-S", str(-lines))
        if result.returncode != 0:
            return None
        return result.stdout.rstrip()

    def send_text(self, pane_id: str, text: str) -> bool:
        pane_id = str(pane_id)
        fd, tmp_path = tempfile.mkstemp(suffix=".txt", prefix="cortex-send-")
        try:
            os.write(fd, text.encode())
            os.close(fd)
            result = self._run("load-buffer", tmp_path)
            if result.returncode != 0:
                return False
            result = self._run("paste-buffer", "-d", "-t", pane_id)
            if result.returncode != 0:
                return False
        finally:
            os.unlink(tmp_path)
        result = self._run("send-keys", "-t", pane_id, "Enter")
        return result.returncode == 0

    def send_keys(self, pane_id: str, keys: str) -> bool:
        result = self._run("send-keys", "-t", str(pane_id), keys)
        return result.returncode == 0

    def focus(self, pane_id: str) -> None:
        pane_id = str(pane_id)
        self._run("select-pane", "-t", pane_id)
        self._run("select-window", "-t", pane_id)

    def wait_for_idle(self, pane_id: str, timeout: int = 30) -> bool:
        for _ in range(timeout):
            output = self.capture_output(pane_id, lines=10)
            if output is None:
                return False
            tail = "\n".join(output.rsplit("\n", 10)[-10:])
            if "❯" in tail:
                return True
            time.sleep(1)
        return False

    def list_pane_ids(self) -> set[str]:
        result = self._run("list-panes", "-a", "-F", "#{pane_id}")
        if result.returncode != 0:
            return set()
        return {line.strip() for line in result.stdout.strip().splitlines() if line.strip()}

    def is_running(self) -> bool:
        result = self._run("list-sessions")
        return result.returncode == 0

    # ── tmux-specific spatial operations ─────────────────────

    def split_window(
        self,
        cwd: str,
        shell_cmd: str,
        *,
        orientation: str = "h",
        target_pane: str | None = None,
    ) -> str | None:
        args = ["split-window", f"-{orientation}", "-d"]
        if target_pane:
            args.extend(["-t", target_pane])
        args.extend(["-P", "-F", "#{pane_id}", "-c", cwd, "fish", "-c", shell_cmd])
        result = self._run(*args)
        if result.returncode != 0:
            log.error("split_window failed", stderr=result.stderr.strip())
            return None
        return result.stdout.strip() or None

    def has_session(self, name: str) -> bool:
        result = self._run("has-session", "-t", name)
        return result.returncode == 0

    def ensure_session(self, name: str) -> None:
        if not self.has_session(name):
            self._run("new-session", "-d", "-s", name)
            log.info("Created tmux session", session=name)

    def new_session(
        self,
        name: str,
        *,
        detached: bool = True,
        window_name: str | None = None,
        cwd: str | None = None,
        shell_cmd: str | None = None,
    ) -> str | None:
        args = ["new-session"]
        if detached:
            args.append("-d")
        args.extend(["-s", name, "-P", "-F", "#{pane_id}"])
        if window_name:
            args.extend(["-n", window_name])
        if cwd:
            args.extend(["-c", cwd])
        if shell_cmd:
            args.extend(["fish", "-c", shell_cmd])
        result = self._run(*args)
        if result.returncode != 0:
            return None
        return result.stdout.strip() or None

    def new_window(
        self,
        *,
        target_session: str | None = None,
        window_name: str | None = None,
        cwd: str | None = None,
        shell_cmd: str | None = None,
    ) -> str | None:
        args = ["new-window", "-d", "-P", "-F", "#{pane_id}"]
        if target_session:
            args.extend(["-t", target_session])
        if window_name:
            args.extend(["-n", window_name])
        if cwd:
            args.extend(["-c", cwd])
        if shell_cmd:
            args.extend(["fish", "-c", shell_cmd])
        result = self._run(*args)
        if result.returncode != 0:
            return None
        return result.stdout.strip() or None

    def break_pane(self, pane_id: str, *, detached: bool = True) -> str | None:
        args = ["break-pane", "-s", pane_id, "-P", "-F", "#{session_name}:#{window_index}.#{pane_id}"]
        if detached:
            args.append("-d")
        result = self._run(*args)
        if result.returncode != 0:
            log.error("break_pane failed", stderr=result.stderr.strip())
            return None
        return result.stdout.strip() or None

    def join_pane(self, source: str, target: str, *, vertical: bool = True) -> bool:
        orientation = "-v" if vertical else "-h"
        result = self._run("join-pane", "-s", source, "-t", target, orientation)
        return result.returncode == 0

    def move_pane(self, source: str, target: str, orientation: str = "-h") -> bool:
        result = self._run("move-pane", "-s", source, "-t", target, orientation)
        return result.returncode == 0

    def move_window(self, source: str, target: str) -> bool:
        result = self._run("move-window", "-s", source, "-t", target)
        return result.returncode == 0

    def kill_window(self, target: str) -> None:
        self._run("kill-window", "-t", target, check=True)

    def select_layout(self, target: str, layout: str) -> None:
        self._run("select-layout", "-t", target, layout)

    def display_message(self, target: str, fmt: str) -> str | None:
        result = self._run("display-message", "-t", target, "-p", fmt)
        if result.returncode != 0:
            return None
        return result.stdout.strip()

    def set_pane_option(self, pane_id: str, option: str, value: str) -> None:
        self._run("set-option", "-p", "-t", pane_id, option, value)

    def list_panes_formatted(self, fmt: str, *, target: str | None = None, all_sessions: bool = True) -> list[str]:
        args = ["list-panes"]
        if all_sessions:
            args.append("-a")
        if target:
            args.extend(["-t", target])
        args.extend(["-F", fmt])
        result = self._run(*args)
        if result.returncode != 0:
            return []
        return [line for line in result.stdout.strip().splitlines() if line.strip()]

    def list_windows(self, target: str, fmt: str = "#{window_name}") -> list[str]:
        result = self._run("list-windows", "-t", target, "-F", fmt)
        if result.returncode != 0:
            return []
        return [line.strip() for line in result.stdout.strip().splitlines() if line.strip()]

    def spawn_background_sender(self, pane_id: str, slash_command: str) -> None:
        """Launch a background fish process that waits for the pane to be idle, then sends a slash command."""
        from pathlib import Path

        log_file = Path.home() / ".cortex" / "logs" / "post-spawn-sender.log"
        send_script = (
            f"set log_file {log_file}; "
            f"echo (date) 'Post-spawn sender started for pane {pane_id}' >> $log_file; "
            f"set attempt 0; "
            f"while not tmux capture-pane -t {pane_id} -p 2>/dev/null | grep -q '❯'; "
            f"set attempt (math $attempt + 1); "
            f'echo (date) "Attempt $attempt: waiting for prompt on pane {pane_id}" >> $log_file; '
            f"if test $attempt -gt 30; echo (date) 'Timed out after 30 attempts' >> $log_file; exit 1; end; "
            f"sleep 1; end; "
            f"tmux send-keys -t {pane_id} -l '{slash_command}'; "
            f"sleep 0.3; tmux send-keys -t {pane_id} Enter; "
            f"echo (date) '{slash_command} sent to {pane_id}' >> $log_file"
        )
        subprocess.Popen(
            ["fish", "-c", send_script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    # ── Internal ─────────────────────────────────────────────

    def _run(self, *args: str, check: bool = False) -> subprocess.CompletedProcess[str]:
        cmd = ["tmux", *args]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if check and result.returncode != 0:
            raise subprocess.CalledProcessError(result.returncode, cmd, result.stdout, result.stderr)
        return result
