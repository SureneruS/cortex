"""Cron executor — polls MongoDB for due jobs and executes them."""

from __future__ import annotations

import json
import signal
import subprocess
import sys
import time

import structlog

log = structlog.get_logger("cortex.daemon")

POLL_INTERVAL = 60
HUMAN_MSG_POLL_INTERVAL = 10


def execute_check_watches(job: dict) -> None:
    from cortex import github
    from cortex.session_registry import MongoSessionRepo
    from cortex.mongo import get_db

    db = get_db()
    session_repo = MongoSessionRepo(db)

    sessions = session_repo.list({"status": "watching"})
    if not sessions:
        log.info("check_watches_empty")
        return

    log.info("check_watches_start", count=len(sessions))

    for session in sessions:
        watch = session.get("watch", {})
        session_name = session.get("name", session["_id"])

        if watch.get("type") == "alarm":
            _handle_alarm(session, watch, session_repo)
            continue

        if watch.get("type") != "pr":
            log.warning("unknown_watch_type", session=session_name, watch_type=watch.get("type"))
            continue

        repo = watch.get("repo")
        number = watch.get("number")
        pr_ref = f"{repo}#{number}"
        last_state = watch.get("last_state", {})

        if not repo or not number:
            log.error("incomplete_watch_data", session=session_name, repo=repo, number=number)
            continue

        log.info("pr_check_start", session=session_name, pr=pr_ref)

        try:
            current_state = github.pr_state(number, repo)
        except Exception as e:
            log.error("pr_state_fetch_failed", session=session_name, pr=pr_ref, error=str(e))
            continue

        if current_state == last_state:
            log.info("pr_no_changes", session=session_name, pr=pr_ref)
            continue

        changes = _detect_pr_changes(last_state, current_state)

        if not changes:
            log.info("pr_baseline_updated", session=session_name, pr=pr_ref)
            session_repo.update(
                session["_id"], {"watch": {**watch, "last_state": current_state}}, trigger="cron", actor="daemon"
            )
            continue

        change_summary = "; ".join(changes)
        log.info("pr_changes_detected", session=session_name, pr=pr_ref, changes=change_summary)

        message = _compose_wake_message(repo, number, change_summary, watch.get("message"), last_state, current_state)
        log.info("pr_waking_session", session=session_name, pr=pr_ref, message=message[:200])

        result = subprocess.run(
            ["cortex", "session", "message", session_name, message],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            log.error("pr_wake_send_failed", session=session_name, pr=pr_ref, stderr=result.stderr.strip())
            # Keep watching so we retry next cycle
            continue

        log.info("pr_wake_sent", session=session_name, pr=pr_ref)

        # Wake the session — babysit skill will re-register watch after handling
        session_repo.update(
            session["_id"],
            {
                "status": "active",
                "runtime": "working",
                "watch": {**watch, "last_state": current_state},
            },
            trigger="cron",
            actor="daemon",
        )

    log.info("check_watches_done", count=len(sessions))


def _handle_alarm(session: dict, watch: dict, session_repo) -> None:
    from datetime import datetime, timezone

    session_name = session.get("name", session["_id"])
    wake_at = datetime.fromisoformat(watch["wake_at"])
    if wake_at > datetime.now(timezone.utc):
        return

    log.info("alarm_triggered", session=session_name)
    result = subprocess.run(
        ["cortex", "session", "message", session_name, watch.get("message", "Alarm triggered")],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        log.error("alarm_send_failed", session=session_name, stderr=result.stderr.strip())
    session_repo.update(session["_id"], {"status": "active", "runtime": "working"}, trigger="cron", actor="daemon")


def _detect_pr_changes(last_state: dict, current_state: dict) -> list[str]:
    changes = []
    if current_state.get("state") != last_state.get("state"):
        changes.append(f"PR state: {last_state.get('state')} -> {current_state.get('state')}")
    if current_state.get("reviewDecision") != last_state.get("reviewDecision"):
        changes.append(f"Review: {last_state.get('reviewDecision')} -> {current_state.get('reviewDecision')}")
    if current_state.get("commentCount", 0) > last_state.get("commentCount", 0):
        diff = current_state["commentCount"] - last_state.get("commentCount", 0)
        changes.append(f"{diff} new comment(s)")
    if current_state.get("reviewCount", 0) > last_state.get("reviewCount", 0):
        diff = current_state["reviewCount"] - last_state.get("reviewCount", 0)
        changes.append(f"{diff} new review(s)")

    old_ci = last_state.get("ciChecks", {})
    new_ci = current_state.get("ciChecks", {})
    for check_name, new_status in new_ci.items():
        old_status = old_ci.get(check_name)
        if old_status and old_status != new_status:
            changes.append(f"CI '{check_name}': {old_status} -> {new_status}")

    old_unresolved = last_state.get("unresolvedThreadCount", 0)
    new_unresolved = current_state.get("unresolvedThreadCount", 0)
    if new_unresolved != old_unresolved:
        changes.append(f"Unresolved threads: {old_unresolved} -> {new_unresolved}")

    return changes


def _compose_wake_message(repo: str, number: int, change_summary: str, custom_message: str | None, last_state: dict, current_state: dict) -> str:
    if custom_message:
        return f"{custom_message}\n\nContext: PR #{number} on {repo} changed — {change_summary}"

    prompt = f"""PR #{number} on {repo} has changes:
{change_summary}

Old state: {json.dumps(last_state, indent=2)}
New state: {json.dumps(current_state, indent=2)}

Compose a brief, specific wake-up message for the worker session. End with "Handle using /babysit-pr {number}".
Output ONLY the message text, nothing else."""

    fallback = f"PR #{number} changed: {change_summary}. Handle using /babysit-pr {number}"
    try:
        result = subprocess.run(
            ["claude", "-p", "--model", "haiku", prompt],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        log.warning("claude_compose_failed", returncode=result.returncode, stderr=result.stderr[:200])
        return fallback
    except subprocess.TimeoutExpired:
        log.warning("claude_compose_timeout")
        return fallback
    except Exception as e:
        log.warning("claude_compose_error", error=str(e))
        return fallback


def execute_command(job: dict) -> None:
    args = job.get("action_args", {})
    command = args.get("command")
    if not command:
        log.error("command_missing", job=job.get("name"))
        return
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=60)
        log.info("command_executed", command=command, returncode=result.returncode, stdout=result.stdout[:200])
        if result.returncode != 0:
            log.warning("command_nonzero_exit", command=command, returncode=result.returncode, stderr=result.stderr[:200])
    except subprocess.TimeoutExpired:
        log.error("command_timeout", command=command)


EXECUTORS = {
    "check-watches": execute_check_watches,
    "command": execute_command,
}


_slack_poster = None
_slack_channel = None


def _read_arc_slack_config() -> tuple[str | None, str | None]:
    """Read Slack credentials from ~/.claude.json arc MCP config."""
    import json
    from pathlib import Path

    claude_json = Path.home() / ".claude.json"
    if not claude_json.exists():
        return None, None
    try:
        data = json.loads(claude_json.read_text())
        arc_env = data.get("mcpServers", {}).get("arc", {}).get("env", {})
        return arc_env.get("SLACK_BOT_TOKEN"), arc_env.get("SLACK_TARGET_USER_ID")
    except Exception:
        return None, None


def _get_slack():
    import os

    global _slack_poster, _slack_channel
    if _slack_poster and _slack_channel:
        return _slack_poster, _slack_channel

    token = os.environ.get("SLACK_BOT_TOKEN")
    user_id = os.environ.get("SLACK_TARGET_USER_ID")
    if not token or not user_id:
        token, user_id = _read_arc_slack_config()
    if not token or not user_id:
        return None, None

    from nova.slack import SlackPoster

    _slack_poster = SlackPoster(bot_token=token, target_user_id=user_id)
    _slack_channel = _slack_poster.get_dm_channel()
    return _slack_poster, _slack_channel


def deliver_human_messages(db) -> None:
    """Poll for to='human' pending messages and deliver via Arc Slack."""
    from datetime import datetime, timezone

    messages_col = db["messages"]
    pending = list(
        messages_col.find({"to": "human", "status": "pending"})
        .sort("created_at", 1)
        .limit(10)
    )
    if not pending:
        return

    for msg in pending:
        claimed = messages_col.find_one_and_update(
            {"_id": msg["_id"], "status": "pending"},
            {"$set": {"status": "delivered", "delivered_at": datetime.now(timezone.utc).isoformat()}},
        )
        if not claimed:
            continue

        sender = msg.get("from", "unknown")
        content = msg.get("content", "")
        meta = msg.get("meta", {})
        msg_type = meta.get("type", "notification")

        slack_text = f"*[{sender}]* ({msg_type})\n{content}"

        poster, channel = _get_slack()
        if poster and channel:
            try:
                poster.post_notification(
                    channel=channel, text=slack_text, username="Arc"
                )
                log.info("human_msg_delivered", msg_id=msg["_id"], sender=sender)
            except Exception as e:
                log.error("human_msg_slack_failed", msg_id=msg["_id"], error=str(e))
                _write_human_message_fallback(msg)
        else:
            log.warning("human_msg_no_slack", msg_id=msg["_id"])
            _write_human_message_fallback(msg)


def _write_human_message_fallback(msg: dict) -> None:
    """Write undelivered human message to file for manual pickup."""
    from pathlib import Path

    fallback_dir = Path.home() / ".cortex" / "human-messages"
    fallback_dir.mkdir(parents=True, exist_ok=True)
    fallback_file = fallback_dir / f"{msg['_id']}.txt"
    fallback_file.write_text(
        f"From: {msg.get('from', '?')}\n"
        f"Time: {msg.get('created_at', '?')}\n"
        f"Type: {(msg.get('meta') or {}).get('type', '?')}\n"
        f"---\n"
        f"{msg.get('content', '')}\n"
    )
    log.info("human_msg_fallback_written", path=str(fallback_file))


# Daemon ID stored at module level for signal handler access
_daemon_id: str | None = None
_shutdown_requested = False


def _shutdown_handler(signum, frame) -> None:
    global _shutdown_requested
    sig_name = signal.Signals(signum).name
    log.info("shutdown_signal_received", signal=sig_name)
    _shutdown_requested = True


def _cleanup_registry() -> None:
    if not _daemon_id:
        return
    try:
        from cortex.session_registry import MongoSessionRepo
        from cortex.mongo import get_db
        db = get_db()
        session_repo = MongoSessionRepo(db)
        session_repo.update(_daemon_id, {"status": "completed"}, trigger="shutdown", actor="daemon")
        log.info("daemon_registry_cleaned", daemon_id=_daemon_id)
    except Exception as e:
        log.error("daemon_registry_cleanup_failed", error=str(e))


def _sweep_stale_daemons(session_repo) -> None:
    """Mark any previously active daemon entries as dead."""
    stale = session_repo.list({"role": "daemon", "status": "active"})
    for s in stale:
        session_repo.update(s["_id"], {"status": "dead"}, trigger="stale-sweep", actor="daemon")
        log.info("stale_daemon_swept", daemon_id=s["_id"])


def run() -> None:
    global _daemon_id

    from cortex.observability import setup_logging
    setup_logging("daemon", force=True)

    from cortex.cron import CronManager
    from cortex.mongo import get_db

    signal.signal(signal.SIGTERM, _shutdown_handler)
    signal.signal(signal.SIGINT, _shutdown_handler)

    log.info("daemon_starting", poll_interval=POLL_INTERVAL)
    db = get_db()
    cron = CronManager(db)

    from cortex.session_registry import MongoSessionRepo, _new_id

    session_repo = MongoSessionRepo(db)

    _sweep_stale_daemons(session_repo)

    _daemon_id = _new_id()
    session_repo.register(
        _daemon_id,
        {
            "name": "cortex-daemon",
            "role": "daemon",
            "goal": "Background cron executor — polls and executes scheduled jobs",
            "status": "active",
        },
    )
    log.info("daemon_registered", daemon_id=_daemon_id)

    cron_counter = 0

    try:
        while not _shutdown_requested:
            try:
                deliver_human_messages(db)
            except Exception as e:
                log.error("human_msg_delivery_error", error=str(e))

            cron_counter += HUMAN_MSG_POLL_INTERVAL
            if cron_counter >= POLL_INTERVAL:
                cron_counter = 0
                try:
                    due = cron.get_due_jobs()
                    if due:
                        log.info("cron_jobs_due", count=len(due))
                    for job in due:
                        action = job["action"]
                        executor = EXECUTORS.get(action)
                        if not executor:
                            log.error("unknown_action", action=action, job=job.get("name"))
                            cron.mark_run(job["name"])
                            continue
                        try:
                            log.info("job_executing", job=job["name"], action=action)
                            executor(job)
                        except Exception as e:
                            log.error("job_failed", job=job["name"], error=str(e), exc_info=True)
                        cron.mark_run(job["name"])
                except Exception as e:
                    log.error("cron_loop_error", error=str(e), exc_info=True)

            time.sleep(HUMAN_MSG_POLL_INTERVAL)
    finally:
        log.info("daemon_shutting_down")
        _cleanup_registry()
        log.info("daemon_stopped")
        sys.exit(0)


if __name__ == "__main__":
    run()
