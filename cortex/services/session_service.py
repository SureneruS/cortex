from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from pathlib import Path

import structlog

from cortex.domain.protocols import MessageRepository, SessionRepository, TerminalAdapter
from cortex.domain.session_states import TERMINAL
from cortex.repositories.session_repo import _new_id

log = structlog.get_logger("cortex.session_service")

CC_COLORS = ["blue", "green", "yellow", "purple", "orange", "pink", "cyan", "red"]


MAX_ACTIVE_SESSIONS = 15


class SessionNotFound(Exception):
    def __init__(self, ref: str) -> None:
        self.ref = ref
        super().__init__(f"Session not found: {ref}")


class SpawnDenied(Exception):
    pass


class ClosePermissionDenied(Exception):
    pass


class SessionService:
    def __init__(
        self,
        sessions: SessionRepository,
        messages: MessageRepository,
        terminal: TerminalAdapter,
    ) -> None:
        self._sessions = sessions
        self._messages = messages
        self._terminal = terminal

    @staticmethod
    def _caller() -> str | None:
        return os.environ.get("CORTEX_SESSION_NAME")

    # ── Resolution ───────────────────────────────────────────

    def resolve(self, ref: str) -> dict:
        try:
            doc = self._sessions.resolve(ref)
        except ValueError:
            raise
        if doc is None:
            raise SessionNotFound(ref)
        return doc

    # ── Spawn ────────────────────────────────────────────────

    def spawn(
        self,
        *,
        name: str,
        goal: str | None = None,
        prompt: str | None = None,
        workspace: str = "default",
        model: str | None = None,
        resume_id: str | None = None,
        repo_path: Path | None = None,
        permission_mode: str | None = None,
        effort: str | None = None,
        agent_name: str | None = None,
        allowed_tools: str | None = None,
        worktree: str | None = None,
        beside: str | None = None,
        below: str | None = None,
        color: str | None = None,
        custom_command: str | None = None,
    ) -> dict:
        self._check_spawn_limit()

        name = self._unique_name(name)
        session_id = _new_id()
        spawned_by = os.environ.get("CORTEX_SESSION_NAME", "cli")
        parent_id = os.environ.get("CORTEX_SESSION_ID")

        if not color:
            color = self._pick_color()

        # Resolve parent info for tracking
        parent_name: str | None = None
        if parent_id:
            parent_doc = self._sessions.get(parent_id)
            if parent_doc:
                parent_name = parent_doc.get("name")

        data = {
            "name": name,
            "workspace": workspace,
            "spawned_by": spawned_by,
            "role": "worker",
            "runtime": "unknown",
            "color": color,
            "parent_id": parent_id,
        }
        if goal:
            data["goal"] = goal
        if model:
            data["model"] = model
        if resume_id:
            data["cc_session_id"] = resume_id
            data["resumed_from"] = resume_id
        if repo_path:
            data["repos"] = [repo_path.name]

        self._sessions.register(session_id, data)
        log.info("Session registered", session_id=session_id, name=name)

        prompt_file = self._write_system_prompt(session_id, name, parent_name=parent_name)

        # Resolve spatial targets
        target_pane, split_orientation = self._resolve_spatial_target(beside, below)
        cwd = str(repo_path) if repo_path else os.getcwd()

        if custom_command:
            # Custom command: use legacy fish -c approach
            env_cmd = self._build_env_cmd(
                session_id=session_id, name=name, parent_id=parent_id, parent_name=parent_name,
            )
            fish_cmd = f"{env_cmd}; {custom_command}"
            pane_id = self._create_pane(
                cwd=cwd, shell_cmd=fish_cmd, workspace=workspace,
                target_pane=target_pane, split_orientation=split_orientation,
            )
        else:
            # Interactive pane: create shell, then send env + claude command
            pane_id = self._create_pane(
                cwd=cwd, workspace=workspace,
                target_pane=target_pane, split_orientation=split_orientation,
            )

        if pane_id:
            self._sessions.update(session_id, {"pane_id": pane_id})

            if not custom_command:
                # Send env vars and claude command as separate send-keys
                env_cmd = self._build_env_cmd(
                    session_id=session_id, name=name, parent_id=parent_id, parent_name=parent_name,
                )
                claude_cmd = self._build_claude_cmd(
                    name=name, model=model, resume_id=resume_id,
                    permission_mode=permission_mode, effort=effort,
                    agent_name=agent_name, allowed_tools=allowed_tools,
                    worktree=worktree, prompt_file=prompt_file,
                )
                self._terminal.send_text(pane_id, env_cmd)
                time.sleep(0.3)
                self._terminal.send_text(pane_id, claude_cmd)

            # Auto-accept channels confirmation
            time.sleep(1)
            self._terminal.send_keys(pane_id, "Enter")

            if prompt:
                self._deliver_prompt(session_id, name, prompt)

            if color:
                self._terminal.spawn_background_sender(pane_id, f"/color {color}")

            log.info("Session spawned", name=name, pane_id=pane_id)
        else:
            self._sessions.update(session_id, {"status": "closed"}, trigger="spawn-fail", actor=self._caller())
            log.error("Spawn failed — no pane_id from terminal")

        result = {
            "session_id": session_id,
            "name": name,
            "workspace": workspace,
            "pane_id": pane_id,
        }
        if goal:
            result["goal"] = goal
        return result

    # ── Close ────────────────────────────────────────────────

    def close(self, ref: str, *, force: bool = False, cascade: bool = False, from_hook: bool = False) -> dict:
        doc = self.resolve(ref)
        session_id = doc["_id"]

        if doc.get("status") in ("completed", "closed"):
            log.info("Session already closed", session_id=session_id, status=doc["status"])
            return doc

        if not from_hook:
            self._check_close_permission(session_id)

        if cascade:
            self._close_descendants(session_id, force=force)

        return self._close_single(doc, force=force)

    def _close_single(self, doc: dict, *, force: bool = False) -> dict:
        session_id = doc["_id"]
        session_name = doc.get("name", session_id)
        pane_id = doc.get("pane_id")

        if doc.get("status") in ("completed", "closed"):
            return doc

        expired = self._messages.expire_for_session(session_name)
        if expired:
            log.info("Expired pending messages", count=expired, session=session_name)

        pane_alive = pane_id is not None and self._terminal.pane_exists(pane_id)

        if force:
            # Force close: status=closed, destroy pane
            self._sessions.update(
                session_id, {"status": "closed", "closed_at": datetime.now(timezone.utc).isoformat()},
                trigger="close-force", actor=self._caller(),
            )
            if pane_alive:
                self._terminal.destroy_pane(pane_id)
        else:
            # Graceful close: status=completed first, then signal CC to exit, then kill pane
            # SessionEnd hook will see completed → no-op
            self._sessions.close(session_id, actor=self._caller())
            if pane_alive:
                self._terminal.send_text(pane_id, "/exit")
                time.sleep(2)
                if self._terminal.pane_exists(pane_id):
                    self._terminal.destroy_pane(pane_id)

        doc = self._sessions.get(session_id)
        log.info("Session closed", session_id=session_id, force=force)
        return doc

    def wrapup(self, ref: str) -> bool:
        """Run wrapup routine on a session (separate from close)."""
        doc = self.resolve(ref)
        session_id = doc["_id"]
        session_name = doc.get("name", session_id)
        pane_id = doc.get("pane_id")
        pane_alive = pane_id is not None and self._terminal.pane_exists(pane_id)

        if not pane_alive:
            log.warning("Cannot wrapup — no live pane", session=session_name)
            return False

        ok = self._wrapup_via_channels(session_name, session_id, pane_id)
        if not ok and self._terminal.pane_exists(pane_id):
            log.warning("Channels wrapup timed out, falling back to terminal send")
            if self._terminal.send_text(pane_id, "/session-wrapup"):
                ok = self._terminal.wait_for_idle(pane_id, timeout=30)

        log.info("Wrapup completed", session=session_name, ok=ok)
        return ok

    def _close_descendants(self, session_id: str, *, force: bool = False) -> list[dict]:
        children = self._sessions.list({
            "parent_id": session_id,
            "status": {"$nin": ["completed", "closed"]},
        })
        closed = []
        for child in children:
            closed.extend(self._close_descendants(child["_id"], force=force))
            closed.append(self._close_single(child, force=force))
        return closed

    def _check_close_permission(self, target_id: str) -> None:
        caller_id = os.environ.get("CORTEX_SESSION_ID")
        if not caller_id:
            return
        if caller_id == target_id:
            return

        current = self._sessions.get(target_id)
        while current:
            pid = current.get("parent_id")
            if pid == caller_id:
                return
            if not pid:
                break
            current = self._sessions.get(pid)

        raise ClosePermissionDenied(
            f"Session '{caller_id}' cannot close '{target_id}' — not an ancestor or self"
        )

    # ── Pause ────────────────────────────────────────────────

    def pause(self, ref: str) -> dict:
        doc = self.resolve(ref)
        session_id = doc["_id"]
        pane_id = doc.get("pane_id")

        if not pane_id or not self._terminal.pane_exists(pane_id):
            raise ValueError(f"No live pane for session '{doc.get('name', session_id)}'")
        if doc.get("status") == "paused":
            raise ValueError("Session is already paused")

        self._terminal.send_text(pane_id, "/exit")
        # Keep pane alive — user can resume or restart CC manually
        self._sessions.update(session_id, {"status": "paused"}, trigger="pause", actor=self._caller())
        doc = self._sessions.get(session_id)
        log.info("Session paused", session_id=session_id)
        return doc

    # ── Resume ───────────────────────────────────────────────

    def resume(self, ref: str) -> dict:
        doc = self.resolve(ref)
        session_id = doc["_id"]

        if doc.get("status") not in ("paused", "completed", "closed"):
            raise ValueError(f"Session is {doc.get('status')}, not paused")

        cc_session_id = doc.get("cc_session_id")
        if not cc_session_id:
            raise ValueError("No cc_session_id — session was never started")

        spawn_result = self.spawn(
            name=doc.get("name", session_id),
            resume_id=cc_session_id,
            repo_path=Path.home() / "workspace" / "cercli" / doc["repos"][0] if doc.get("repos") else None,
            color=doc.get("color"),
            model=doc.get("model"),
        )

        new_session_id = spawn_result["session_id"]
        new_pane_id = spawn_result.get("pane_id")

        self._sessions.update(session_id, {
            "status": "active",
            "pane_id": new_pane_id,
            "resumed_session_id": new_session_id,
        }, trigger="resume", actor=self._caller())

        self._sessions.update(new_session_id, {
            "status": "completed",
            "shadow_of": session_id,
        }, trigger="resume-link", actor=self._caller())

        doc = self._sessions.get(session_id)
        log.info("Session resumed", session_id=session_id, pane_id=new_pane_id)
        return doc

    # ── Hide / Show ──────────────────────────────────────────

    def hide(self, ref: str) -> dict:
        doc = self.resolve(ref)
        session_id = doc["_id"]
        pane_id = doc.get("pane_id")

        if not pane_id or not self._terminal.pane_exists(pane_id):
            raise ValueError(f"No live pane for session '{doc.get('name', session_id)}'")

        self._terminal.ensure_session("background")

        location = self._terminal.break_pane(pane_id)
        if not location:
            raise RuntimeError("break-pane failed")

        src_session = location.split(":")[0] if ":" in location else "work"
        window_part = location.split(":")[1].split(".")[0] if ":" in location else "0"
        src_target = f"{src_session}:{window_part}"

        if not self._terminal.move_window(src_target, "background:"):
            raise RuntimeError("move-window failed")

        self._sessions.update(session_id, {
            "pane_id": pane_id,
            "hidden_from": src_session,
            "workspace": "background",
        }, trigger="hide", actor=self._caller())

        doc = self._sessions.get(session_id)
        log.info("Session hidden", session_id=session_id)
        return doc

    def show(self, ref: str) -> dict:
        doc = self.resolve(ref)
        session_id = doc["_id"]

        if not doc.get("hidden_from"):
            raise ValueError(f"Session '{doc.get('name', session_id)}' is not in a background workspace")

        pane_id = doc.get("pane_id")
        if not pane_id or not self._terminal.pane_exists(pane_id):
            raise ValueError("Pane is dead — use resume instead")

        src_target = self._terminal.display_message(pane_id, "#{session_name}:#{window_index}")
        target_session = doc.get("hidden_from", "work")

        if not self._terminal.move_window(src_target, f"{target_session}:"):
            raise RuntimeError("move-window failed")

        self._sessions.update(session_id, {"hidden_from": None, "workspace": "default"}, trigger="show", actor=self._caller())
        doc = self._sessions.get(session_id)
        log.info("Session shown", session_id=session_id)
        return doc

    # ── Health ───────────────────────────────────────────────

    def health_check(self) -> dict:
        live_panes = self._terminal.list_pane_ids()
        sessions = self._sessions.list({"status": {"$nin": ["completed", "closed"]}})
        registry_panes: set[str] = set()
        findings: list[dict] = []

        for doc in sessions:
            pane_id = doc.get("pane_id")
            session_id = doc["_id"]
            name = doc.get("name", session_id)
            if pane_id:
                registry_panes.add(str(pane_id))

            if pane_id is None or str(pane_id) not in live_panes:
                if doc.get("status") in ("active", "idle"):
                    self._sessions.update(
                        session_id, {"status": "paused", "runtime": "unknown"}, trigger="health-check", actor="system"
                    )
                    findings.append({
                        "severity": "warning",
                        "check": "pane_gone",
                        "session_id": session_id,
                        "name": name,
                        "pane_id": pane_id,
                        "message": f"Session '{name}' has no live pane — marked paused",
                    })
                continue

            output = self._terminal.capture_output(pane_id, lines=10)
            if output and "❯" in output:
                runtime = "waiting_input"
            else:
                runtime = "working"
            self._sessions.update_runtime(session_id, runtime)

            age_h = self._event_age_hours(doc)
            if age_h is not None and age_h > 24:
                findings.append({
                    "severity": "warning",
                    "check": "stale",
                    "session_id": session_id,
                    "name": name,
                    "hours_since_activity": round(age_h, 1),
                    "message": f"Session '{name}' has had no activity for {round(age_h, 1)}h",
                })

            findings.append({
                "severity": "info",
                "check": "runtime",
                "session_id": session_id,
                "name": name,
                "pane_id": pane_id,
                "runtime": runtime,
                "status": doc.get("status"),
            })

        # Untracked panes
        untracked = live_panes - registry_panes
        for pane_id in sorted(untracked):
            title = self._terminal.display_message(pane_id, "#{pane_title}") or ""
            findings.append({
                "severity": "info",
                "check": "untracked_pane",
                "pane_id": pane_id,
                "pane_title": title,
                "message": f"Pane {pane_id} ('{title}') not in session registry",
            })

        severity_order = {"critical": 0, "warning": 1, "info": 2}
        findings.sort(key=lambda f: severity_order.get(f["severity"], 9))

        summary = {
            "total_sessions": len(sessions),
            "critical": sum(1 for f in findings if f["severity"] == "critical"),
            "warning": sum(1 for f in findings if f["severity"] == "warning"),
            "info": sum(1 for f in findings if f["severity"] == "info"),
        }
        return {"summary": summary, "findings": findings}

    # ── Cleanup ──────────────────────────────────────────────

    def cleanup(self) -> list[dict]:
        sessions = self._sessions.list({"status": {"$nin": ["completed", "closed"]}})
        closed = []
        for doc in sessions:
            pane_id = doc.get("pane_id")
            if pane_id is None or not self._terminal.pane_exists(pane_id):
                session_id = doc["_id"]
                self._sessions.close(session_id, trigger="cleanup", actor="system")
                closed.append({"session_id": session_id, "name": doc.get("name"), "pane_id": pane_id})
        return closed

    # ── Attach / Capture ─────────────────────────────────────

    def attach(self, ref: str) -> dict:
        doc = self.resolve(ref)
        pane_id = doc.get("pane_id")
        if not pane_id:
            raise ValueError("Session has no pane_id")
        if not self._terminal.pane_exists(pane_id):
            raise ValueError(f"Pane {pane_id} does not exist")
        self._terminal.focus(pane_id)
        return doc

    def capture(self, ref: str, lines: int = 50) -> dict:
        doc = self.resolve(ref)
        pane_id = doc.get("pane_id")
        if pane_id is None or not self._terminal.pane_exists(pane_id):
            raise ValueError(f"Pane not available for session {doc['_id']}")
        output = self._terminal.capture_output(pane_id, lines=lines) or ""
        return {"session_id": doc["_id"], "pane_id": pane_id, "output": output}

    # ── Message ──────────────────────────────────────────────

    def send_message(
        self,
        recipient: str,
        content: str,
        *,
        thread_id: str | None = None,
        extra_meta: dict | None = None,
    ) -> dict:
        import uuid

        if recipient != "human":
            terminal_values = [s.value for s in TERMINAL]
            sessions = self._sessions.list({"name": recipient, "status": {"$nin": terminal_values}})
            if not sessions:
                raise SessionNotFound(recipient)

        sender = os.environ.get("CORTEX_SESSION_NAME", "human")
        meta = {
            "type": "request",
            "sender_type": "human" if sender == "human" else "agent",
            "priority": "high",
            "thread_id": thread_id or ("t_" + uuid.uuid4().hex[:12]),
        }
        if extra_meta:
            meta.update(extra_meta)
        msg = self._messages.create(sender, recipient, content, meta=meta)
        return {"success": True, "msg_id": msg.id, "to": recipient}

    # ── Children / Tree ────────────────────────────────────────

    def children(self, ref: str, *, include_dead: bool = False) -> list[dict]:
        doc = self.resolve(ref)
        filters: dict = {"parent_id": doc["_id"]}
        if not include_dead:
            filters["status"] = {"$nin": ["completed", "closed"]}
        return self._sessions.list(filters)

    def tree(self, ref: str | None = None) -> list[dict]:
        if ref:
            root = self.resolve(ref)
            return [self._build_tree_node(root)]

        roots = self._sessions.list({
            "status": {"$nin": ["completed", "closed"]},
            "$or": [
                {"parent_id": None},
                {"parent_id": {"$exists": False}},
            ],
        })
        return [self._build_tree_node(r) for r in roots]

    def _build_tree_node(self, doc: dict) -> dict:
        children = self._sessions.list({
            "parent_id": doc["_id"],
            "status": {"$nin": ["completed", "closed"]},
        })
        node = {
            "session_id": doc["_id"],
            "name": doc.get("name"),
            "status": doc.get("status"),
            "role": doc.get("role"),
            "children": [self._build_tree_node(c) for c in children],
        }
        return node

    # ── Internal helpers ─────────────────────────────────────

    def _check_spawn_limit(self) -> None:
        active = self._sessions.list({"status": {"$in": ["active", "idle", "blocked"]}})
        if len(active) >= MAX_ACTIVE_SESSIONS:
            raise SpawnDenied(
                f"Global session limit reached ({MAX_ACTIVE_SESSIONS} active sessions)"
            )

    def _pick_color(self) -> str:
        active = self._sessions.list({"status": {"$nin": ["completed", "closed"]}})
        used = {doc.get("color") for doc in active if doc.get("color")}
        return next((c for c in CC_COLORS if c not in used), CC_COLORS[0])

    def _unique_name(self, name: str) -> str:
        existing = self._sessions.list(
            {"name": name, "status": {"$nin": ["completed", "closed", "paused"]}}
        )
        if not existing:
            return name
        suffix = 2
        while True:
            candidate = f"{name}-{suffix}"
            matches = self._sessions.list(
                {"name": candidate, "status": {"$nin": ["completed", "closed", "paused"]}}
            )
            if not matches:
                return candidate
            suffix += 1

    def _write_system_prompt(
        self, session_id: str, name: str, *, parent_name: str | None = None,
    ) -> Path:
        prompt_dir = Path.home() / ".cortex" / "session-prompts"
        prompt_dir.mkdir(parents=True, exist_ok=True)
        prompt_file = prompt_dir / f"{session_id}.txt"

        if parent_name:
            system_prompt = (
                f"You are a Cortex worker session (name: {name}, id: {session_id}).\n\n"
                f"You were spawned by '{parent_name}'. Report progress and results back to '{parent_name}'.\n"
                f"You can spawn your own sub-workers with `cortex session spawn` if needed.\n"
                f"When done or asked to wrap up, run /session-wrapup and /exit.\n"
                f"Use /cortex-cli skill for the full command reference."
            )
        else:
            system_prompt = (
                f"You are a Cortex worker session (name: {name}, id: {session_id}).\n\n"
                f"Your role: execute the task you're given. Focus, ship, report back.\n"
                f"A control session coordinates all workers — follow its instructions.\n"
                f"You can spawn sub-workers with `cortex session spawn` if needed.\n"
                f"Report progress and blockers to the control session via messages.\n"
                f"When done or asked to wrap up, run /session-wrapup and /exit.\n"
                f"Use /cortex-cli skill for the full command reference."
            )
        prompt_file.write_text(system_prompt)
        return prompt_file

    def _build_env_cmd(
        self,
        *,
        session_id: str,
        name: str,
        parent_id: str | None = None,
        parent_name: str | None = None,
    ) -> str:
        from cortex.mongo import MONGO_URI, MONGO_DB

        mongodb_uri = f"{MONGO_URI}/{MONGO_DB}"
        parts = [
            "set -x CORTEX_SESSION_ROLE worker",
            f"set -x CORTEX_SESSION_ID {session_id}",
            f"set -x CORTEX_SESSION_NAME {name}",
            f"set -x CORTEX_MONGODB_URI {mongodb_uri}",
        ]
        if parent_id:
            parts.append(f"set -x CORTEX_PARENT_ID {parent_id}")
        if parent_name:
            parts.append(f"set -x CORTEX_PARENT_NAME {parent_name}")
        return "; ".join(parts)

    def _build_claude_cmd(
        self,
        *,
        name: str,
        model: str | None,
        resume_id: str | None,
        permission_mode: str | None,
        effort: str | None,
        agent_name: str | None,
        allowed_tools: str | None,
        worktree: str | None,
        prompt_file: Path,
    ) -> str:
        channels_flag = "--dangerously-load-development-channels server:cortex-team "
        deny_flag = "--disallowedTools SendMessage "
        model_flag = f"--model {model} " if model else ""
        resume_flag = f"--resume {resume_id} " if resume_id else ""
        pm_flag = f"--permission-mode {permission_mode} " if permission_mode else ""
        effort_flag = f"--effort {effort} " if effort else ""
        agent_flag = f"--agent {agent_name} " if agent_name else ""
        tools_flag = f"--allowed-tools {allowed_tools} " if allowed_tools else ""
        wt_flag = f"--worktree {worktree} " if worktree else ""
        cc_flags = f"{pm_flag}{effort_flag}{agent_flag}{tools_flag}{wt_flag}"

        return (
            f"claude {channels_flag}{deny_flag}{model_flag}{resume_flag}{cc_flags}"
            f"--name {name} --append-system-prompt-file {prompt_file}"
        )

    def _resolve_spatial_target(
        self, beside: str | None, below: str | None
    ) -> tuple[str | None, str | None]:
        if beside:
            pane_id = beside if beside.startswith("%") else self.resolve(beside).get("pane_id")
            if not pane_id or not self._terminal.pane_exists(pane_id):
                raise ValueError(f"Cannot resolve --beside target: {beside}")
            return pane_id, "h"
        if below:
            pane_id = below if below.startswith("%") else self.resolve(below).get("pane_id")
            if not pane_id or not self._terminal.pane_exists(pane_id):
                raise ValueError(f"Cannot resolve --below target: {below}")
            return pane_id, "v"
        return None, None

    def _create_pane(
        self,
        *,
        cwd: str,
        shell_cmd: str | None = None,
        workspace: str,
        target_pane: str | None,
        split_orientation: str | None,
    ) -> str | None:
        if workspace == "background":
            self._terminal.ensure_session("background")
            if shell_cmd:
                return self._terminal.create_pane(cwd, shell_cmd, target_session="background")
            return self._terminal.create_interactive_pane(cwd, target_session="background")

        if target_pane and split_orientation:
            if shell_cmd:
                return self._terminal.split_window(
                    cwd, shell_cmd, orientation=split_orientation, target_pane=target_pane
                )
            return self._terminal.split_interactive_window(
                cwd, orientation=split_orientation, target_pane=target_pane
            )

        caller_pane = self._resolve_caller_pane()
        spawn_mode = os.environ.get("CORTEX_SPAWN_MODE", "tab")

        if spawn_mode == "split" and caller_pane:
            if shell_cmd:
                return self._terminal.split_window(
                    cwd, shell_cmd, orientation="h", target_pane=caller_pane
                )
            return self._terminal.split_interactive_window(
                cwd, orientation="h", target_pane=caller_pane
            )

        if shell_cmd:
            return self._terminal.create_pane(cwd, shell_cmd)
        return self._terminal.create_interactive_pane(cwd)

    def _resolve_caller_pane(self) -> str | None:
        caller_id = os.environ.get("CORTEX_SESSION_ID")
        if not caller_id:
            return None
        doc = self._sessions.get(caller_id)
        if doc and doc.get("pane_id"):
            return str(doc["pane_id"])
        return None

    def _deliver_prompt(self, session_id: str, session_name: str, prompt: str) -> None:
        """Deliver prompt via channels with readiness gate and reply verification."""
        # Wait for channel_status="ready" (set by channels MCP on oninitialized)
        for _ in range(60):
            doc = self._sessions.get(session_id)
            if doc and doc.get("channel_status") == "ready":
                break
            time.sleep(1)
        else:
            log.warning("Channel readiness timeout", session=session_name)
            return

        spawned_by = os.environ.get("CORTEX_SESSION_NAME", "cli")
        sent_at = datetime.now(timezone.utc).isoformat()

        self._messages.create(
            spawned_by, session_name, prompt,
            meta={"type": "prompt", "sender_type": "system", "priority": "high"},
        )
        log.info("Prompt sent via channels", session=session_name)

        # Wait for reply to confirm delivery
        for _ in range(15):
            time.sleep(1)
            if self._messages.has_replies(
                from_session=session_name, to_session=spawned_by, after=sent_at,
            ):
                log.info("Prompt delivery confirmed by reply", session=session_name)
                return

        # No reply — resend with fallback notice
        log.warning("No reply to prompt, resending", session=session_name)
        self._messages.create(
            spawned_by, session_name,
            f"Sending again as last message did not get any response — respond to this message immediately: {prompt}",
            meta={"type": "prompt", "sender_type": "system", "priority": "high"},
        )

    def _wrapup_via_channels(self, session_name: str, session_id: str, pane_id: str) -> bool:
        self._messages.create(
            os.environ.get("CORTEX_SESSION_NAME", "human"),
            session_name,
            "Session wrapup requested. Please run /session-wrapup, update your status, and exit.",
            meta={"type": "lifecycle", "action": "wrapup", "sender_type": "system", "priority": "high"},
        )

        for _ in range(30):
            time.sleep(1)
            current = self._sessions.get(session_id)
            if current and current.get("status") in ("completed", "closed"):
                return True
            if not self._terminal.pane_exists(pane_id):
                return True
        return False

    @staticmethod
    def _event_age_hours(doc: dict) -> float | None:
        events = doc.get("events", [])
        ts = events[-1].get("at") if events else doc.get("created_at")
        if not ts:
            return None
        try:
            dt = datetime.fromisoformat(ts)
            return (datetime.now(timezone.utc) - dt).total_seconds() / 3600
        except (ValueError, TypeError):
            return None
