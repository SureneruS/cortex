"""Cron executor — polls MongoDB for due jobs and executes them."""

from __future__ import annotations

import json
import signal
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import structlog

from cortex.domain.routing import (
    HUMAN_RECIPIENT,
    HUMAN_SENDER_TYPE,
    LEGACY_HUMAN_RECIPIENT,
)

log = structlog.get_logger("cortex.daemon")

POLL_INTERVAL = 60
SUREN_MSG_POLL_INTERVAL = 10
HEALTH_CHECK_INTERVAL = 30
HEALTH_MISS_THRESHOLD = 5
ARCHIVE_AFTER_DAYS = 7

FALLBACK_MESSAGES_DIR = Path.home() / ".cortex" / f"{HUMAN_RECIPIENT}-messages"
LEGACY_FALLBACK_MESSAGES_DIR = Path.home() / ".cortex" / f"{LEGACY_HUMAN_RECIPIENT}-messages"


def _log_activity(db, kind: str, summary: str, **details) -> None:
    from datetime import datetime, timezone
    db["activity"].insert_one({
        "kind": kind,
        "summary": summary,
        "details": details,
        "timestamp": datetime.now(timezone.utc),
    })


def execute_check_watches(job: dict) -> None:
    from cortex import github
    from cortex.session_registry import MongoSessionRepo
    from cortex.mongo import get_db

    db = get_db()
    session_repo = MongoSessionRepo(db)

    sessions = session_repo.list({"watch_active": True})
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
            _log_activity(db, "watch", f"PR {pr_ref} checked — no changes", session=session_name, pr=pr_ref)
            continue

        changes = _detect_pr_changes(last_state, current_state)

        if not changes:
            log.info("pr_baseline_updated", session=session_name, pr=pr_ref)
            _log_activity(db, "watch", f"PR {pr_ref} baseline updated", session=session_name, pr=pr_ref)
            session_repo.update(
                session["_id"], {"watch": {**watch, "last_state": current_state}}, trigger="cron", actor="daemon"
            )
            continue

        change_summary = "; ".join(changes)
        log.info("pr_changes_detected", session=session_name, pr=pr_ref, changes=change_summary)

        message = _compose_wake_message(repo, number, change_summary, watch.get("message"), last_state, current_state)
        log.info("pr_waking_session", session=session_name, pr=pr_ref, message=message[:200])

        result = subprocess.run(
            ["cortex", "--json", "session", "message", session_name, message],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            log.error("pr_wake_send_failed", session=session_name, pr=pr_ref, stderr=result.stderr.strip())
            _log_activity(db, "watch", f"PR {pr_ref} wake failed — {result.stderr.strip()[:80]}", session=session_name, pr=pr_ref, error=True)
            # Keep watching so we retry next cycle
            continue

        log.info("pr_wake_sent", session=session_name, pr=pr_ref)
        _log_activity(db, "watch", f"PR {pr_ref} changed — {change_summary}; waking {session_name}", session=session_name, pr=pr_ref, changes=change_summary)

        pr_still_open = current_state.get("state") == "OPEN"
        session_repo.update(
            session["_id"],
            {
                "watch": {**watch, "last_state": current_state},
                "watch_active": pr_still_open,
            },
            trigger="cron",
            actor="daemon",
        )
        if pr_still_open:
            _log_activity(db, "watch", f"PR {pr_ref} watch continues with updated baseline", session=session_name, pr=pr_ref)
        else:
            _log_activity(db, "watch", f"PR watch cleared: {pr_ref} — PR no longer open", session=session_name, pr=pr_ref)

    log.info("check_watches_done", count=len(sessions))


def _handle_alarm(session: dict, watch: dict, session_repo) -> None:
    from datetime import datetime, timezone

    session_name = session.get("name", session["_id"])
    wake_at = datetime.fromisoformat(watch["wake_at"])
    if wake_at > datetime.now(timezone.utc):
        return

    log.info("alarm_triggered", session=session_name)
    result = subprocess.run(
        ["cortex", "--json", "session", "message", session_name, watch.get("message", "Alarm triggered")],
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
_bot_user_id: str | None = None

# In-memory cache: slack_thread_ts → session_name
# Populated on outbound delivery, queried on inbound reply, DB fallback on miss
_thread_session_map: dict[str, str] = {}


def _read_arc_slack_config() -> tuple[str | None, str | None, str | None]:
    """Read Slack credentials from ~/.claude.json arc MCP config."""
    import json
    from pathlib import Path

    claude_json = Path.home() / ".claude.json"
    if not claude_json.exists():
        return None, None, None
    try:
        data = json.loads(claude_json.read_text())
        arc_env = data.get("mcpServers", {}).get("arc", {}).get("env", {})
        return (
            arc_env.get("SLACK_BOT_TOKEN"),
            arc_env.get("SLACK_TARGET_USER_ID"),
            arc_env.get("SLACK_APP_TOKEN"),
        )
    except Exception:
        return None, None, None


_slack_app_token: str | None = None


def _get_slack():
    import os

    global _slack_poster, _slack_channel, _slack_app_token, _bot_user_id
    if _slack_poster and _slack_channel:
        return _slack_poster, _slack_channel

    token = os.environ.get("SLACK_BOT_TOKEN")
    user_id = os.environ.get("SLACK_TARGET_USER_ID")
    app_token = os.environ.get("SLACK_APP_TOKEN")
    if not token or not user_id:
        token, user_id, app_token_cfg = _read_arc_slack_config()
        if not app_token:
            app_token = app_token_cfg
    if not token or not user_id:
        return None, None

    from nova.slack import SlackPoster

    _slack_poster = SlackPoster(bot_token=token, target_user_id=user_id)
    _slack_channel = _slack_poster.get_dm_channel()
    _slack_app_token = app_token

    try:
        from slack_sdk import WebClient
        client = WebClient(token=token)
        resp = client.auth_test()
        _bot_user_id = resp["user_id"]
    except Exception as e:
        log.warning("bot_user_id_fetch_failed", error=str(e))

    return _slack_poster, _slack_channel


def _get_bot_user_id() -> str | None:
    return _bot_user_id


def _get_session_thread(db, session_name: str) -> tuple[str | None, str | None]:
    """Get existing Slack thread for a session. Cache first, DB fallback."""
    for ts, name in _thread_session_map.items():
        if name == session_name:
            return ts, None
    session = db["session_registry"].find_one(
        {"name": session_name, "status": {"$nin": ["completed", "dead"]}},
        {"slack_thread_ts": 1, "slack_channel": 1},
    )
    if session and session.get("slack_thread_ts"):
        _thread_session_map[session["slack_thread_ts"]] = session_name
        return session["slack_thread_ts"], session.get("slack_channel")
    return None, None


def deliver_suren_messages(db) -> None:
    """Poll for messages routed to Suren (to='suren', legacy alias 'human') and deliver via Arc Slack.

    Groups messages into one Slack thread per session — first message from a session
    creates a new thread, subsequent messages reply in it.
    """
    from datetime import datetime, timezone

    messages_col = db["messages"]
    pending = list(
        messages_col.find(
            {"to": {"$in": [HUMAN_RECIPIENT, LEGACY_HUMAN_RECIPIENT]}, "status": "pending"}
        )
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
                thread_ts, _ = _get_session_thread(db, sender)
                slack_ts = poster.post_notification(
                    channel=channel, text=slack_text, username="Arc",
                    thread_ts=thread_ts,
                )
                if not thread_ts:
                    # First message from this session — store thread anchor
                    db["session_registry"].update_one(
                        {"name": sender, "status": {"$nin": ["completed", "dead"]}},
                        {"$set": {"slack_thread_ts": slack_ts, "slack_channel": channel}},
                    )
                    _thread_session_map[slack_ts] = sender
                log.info("suren_msg_delivered", msg_id=msg["_id"], sender=sender, thread_ts=thread_ts or slack_ts)
            except Exception as e:
                log.error("suren_msg_slack_failed", msg_id=msg["_id"], error=str(e))
                _write_suren_message_fallback(msg)
        else:
            log.warning("suren_msg_no_slack", msg_id=msg["_id"])
            _write_suren_message_fallback(msg)


def _write_suren_message_fallback(msg: dict) -> None:
    """Write undelivered Suren message to file for manual pickup."""
    FALLBACK_MESSAGES_DIR.mkdir(parents=True, exist_ok=True)
    fallback_file = FALLBACK_MESSAGES_DIR / f"{msg['_id']}.txt"
    fallback_file.write_text(
        f"From: {msg.get('from', '?')}\n"
        f"Time: {msg.get('created_at', '?')}\n"
        f"Type: {(msg.get('meta') or {}).get('type', '?')}\n"
        f"---\n"
        f"{msg.get('content', '')}\n"
    )
    log.info("suren_msg_fallback_written", path=str(fallback_file))


def _migrate_legacy_fallback_dir() -> None:
    """One-shot migration: move files from ~/.cortex/human-messages/ to ~/.cortex/suren-messages/."""
    if not LEGACY_FALLBACK_MESSAGES_DIR.is_dir():
        return
    FALLBACK_MESSAGES_DIR.mkdir(parents=True, exist_ok=True)
    moved = 0
    for src in LEGACY_FALLBACK_MESSAGES_DIR.iterdir():
        if not src.is_file():
            continue
        dst = FALLBACK_MESSAGES_DIR / src.name
        if dst.exists():
            continue
        src.rename(dst)
        moved += 1
    try:
        LEGACY_FALLBACK_MESSAGES_DIR.rmdir()
    except OSError:
        pass
    if moved:
        log.info(
            "fallback_dir_migrated",
            moved=moved,
            from_=str(LEGACY_FALLBACK_MESSAGES_DIR),
            to=str(FALLBACK_MESSAGES_DIR),
        )


# ── Inbound: Slack replies → session messages ──────────────────


def _resolve_thread_session(db, thread_ts: str) -> str | None:
    """Resolve a Slack thread_ts to a session name. Cache first, DB fallback."""
    if thread_ts in _thread_session_map:
        return _thread_session_map[thread_ts]
    session = db["session_registry"].find_one(
        {"slack_thread_ts": thread_ts, "status": {"$nin": ["completed", "dead"]}},
        {"name": 1},
    )
    if session:
        _thread_session_map[thread_ts] = session["name"]
        return session["name"]
    return None


def handle_slack_message_event(
    db,
    *,
    user: str,
    text: str,
    thread_ts: str | None,
    ts: str,
    channel: str,
    bot_user_id: str | None,
) -> None:
    """Handle an inbound Slack message event. Creates a from='suren' message if it's
    a threaded reply to a known session thread."""
    if not thread_ts:
        return
    if bot_user_id and user == bot_user_id:
        return

    session_name = _resolve_thread_session(db, thread_ts)
    if not session_name:
        log.debug("slack_reply_unknown_thread", thread_ts=thread_ts)
        return

    from datetime import datetime, timezone
    import uuid

    msg_id = "msg_" + uuid.uuid4().hex[:16]
    now = datetime.now(timezone.utc).isoformat()

    db["messages"].insert_one({
        "_id": msg_id,
        "from": HUMAN_RECIPIENT,
        "to": session_name,
        "content": text,
        "meta": {
            "type": "reply",
            "sender_type": HUMAN_SENDER_TYPE,
            "priority": "high",
            "slack_ts": ts,
        },
        "status": "pending",
        "created_at": now,
        "delivered_at": None,
    })
    log.info("slack_reply_routed", msg_id=msg_id, session=session_name, slack_ts=ts)


def start_socket_listener(db) -> None:
    """Start Slack Socket Mode listener in a background thread."""
    poster, channel = _get_slack()
    if not poster or not _slack_app_token:
        log.warning("socket_listener_skipped", reason="no slack config or app token")
        return

    from slack_sdk.socket_mode import SocketModeClient
    from slack_sdk.socket_mode.request import SocketModeRequest
    from slack_sdk.socket_mode.response import SocketModeResponse

    global _socket_mode_client
    _socket_mode_client = SocketModeClient(
        app_token=_slack_app_token,
        web_client=poster._client,
    )

    def _handle_event(client: SocketModeClient, req: SocketModeRequest):
        client.send_socket_mode_response(SocketModeResponse(envelope_id=req.envelope_id))

        if req.type != "events_api":
            return
        event = req.payload.get("event", {})
        if event.get("type") != "message":
            return
        if event.get("subtype"):
            return

        handle_slack_message_event(
            db,
            user=event.get("user", ""),
            text=event.get("text", ""),
            thread_ts=event.get("thread_ts"),
            ts=event.get("ts", ""),
            channel=event.get("channel", ""),
            bot_user_id=_bot_user_id,
        )

    _socket_mode_client.socket_mode_request_listeners.append(_handle_event)
    _socket_mode_client.connect()
    log.info("socket_listener_started")


_socket_mode_client = None


_shutdown_requested = False


def _shutdown_handler(signum, frame) -> None:
    global _shutdown_requested
    sig_name = signal.Signals(signum).name
    log.info("shutdown_signal_received", signal=sig_name)
    _shutdown_requested = True


def _purge_legacy_daemon_entries(db) -> None:
    """One-time migration: remove daemon self-registrations left by older
    daemons that stored themselves in session_registry. Liveness is tracked
    by launchctl now, not by a session entry, so these docs only add noise
    to dashboards and session lists."""
    result = db["session_registry"].delete_many({"role": "daemon"})
    if result.deleted_count:
        log.info("purged_legacy_daemon_entries", count=result.deleted_count)


def _ping_health(session_id: str) -> bool:
    """Ping the channels MCP health endpoint for a session."""
    health_file = Path.home() / ".cortex" / "health" / session_id
    if not health_file.exists():
        return False
    try:
        port = int(health_file.read_text().strip())
        req = urllib.request.Request(f"http://127.0.0.1:{port}/health", method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            return resp.status == 200
    except Exception:
        return False


def run_health_check(session_repo) -> int:
    """Check health of active/idle sessions via channels MCP health endpoint.

    Miss-count based: increment heartbeat_miss_count when health check fails,
    reset when it succeeds. 5 consecutive misses → paused.
    Also archives sessions paused/blocked for 7+ days.
    """
    sessions = session_repo.list({"status": {"$in": ["active", "idle"]}})
    actions = 0

    for doc in sessions:
        session_id = doc["_id"]
        miss_count = doc.get("heartbeat_miss_count", 0)

        if _ping_health(session_id):
            if miss_count > 0:
                session_repo.update(session_id, {"heartbeat_miss_count": 0}, trigger="health-check", actor="daemon")
        else:
            miss_count += 1
            if miss_count >= HEALTH_MISS_THRESHOLD:
                session_repo.update(
                    session_id,
                    {"status": "paused", "heartbeat_miss_count": miss_count},
                    trigger="health-check-miss",
                    actor="daemon",
                )
                log.info("session_paused_by_health_check", session_id=session_id, miss_count=miss_count)
                actions += 1
            else:
                session_repo.update(
                    session_id, {"heartbeat_miss_count": miss_count}, trigger="health-check", actor="daemon",
                )

    # Archive stale paused/blocked sessions
    archive_cutoff = (datetime.now(timezone.utc) - timedelta(days=ARCHIVE_AFTER_DAYS)).isoformat()
    stale = session_repo.list({
        "status": {"$in": ["paused", "blocked"]},
        "events": {"$not": {"$elemMatch": {"at": {"$gte": archive_cutoff}}}},
    })
    for doc in stale:
        last_event_at = doc.get("events", [{}])[-1].get("at", "") if doc.get("events") else ""
        if last_event_at and last_event_at < archive_cutoff:
            session_repo.update(doc["_id"], {"status": "archived"}, trigger="archive-sweep", actor="daemon")
            log.info("session_archived", session_id=doc["_id"])
            actions += 1

    return actions


def run() -> None:
    from cortex.observability import setup_logging
    setup_logging("daemon", force=True)

    from cortex.cron import CronManager
    from cortex.mongo import get_db

    signal.signal(signal.SIGTERM, _shutdown_handler)
    signal.signal(signal.SIGINT, _shutdown_handler)

    log.info("daemon_starting", poll_interval=POLL_INTERVAL)
    db = get_db()
    db["activity"].create_index("timestamp", expireAfterSeconds=7 * 86400)
    cron = CronManager(db)

    from cortex.session_registry import MongoSessionRepo

    session_repo = MongoSessionRepo(db)

    _purge_legacy_daemon_entries(db)
    _migrate_legacy_fallback_dir()

    try:
        start_socket_listener(db)
    except Exception as e:
        log.error("socket_listener_start_failed", error=str(e))

    cron_counter = 0
    health_counter = 0

    try:
        while not _shutdown_requested:
            try:
                deliver_suren_messages(db)
            except Exception as e:
                log.error("suren_msg_delivery_error", error=str(e))

            # Health check every HEALTH_CHECK_INTERVAL seconds
            health_counter += SUREN_MSG_POLL_INTERVAL
            if health_counter >= HEALTH_CHECK_INTERVAL:
                health_counter = 0
                try:
                    actions = run_health_check(session_repo)
                    if actions:
                        log.info("health_check_actions", count=actions)
                except Exception as e:
                    log.error("health_check_error", error=str(e))

            cron_counter += SUREN_MSG_POLL_INTERVAL
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

            time.sleep(SUREN_MSG_POLL_INTERVAL)
    finally:
        log.info("daemon_shutting_down")
        if _socket_mode_client:
            try:
                _socket_mode_client.close()
                log.info("socket_listener_stopped")
            except Exception as e:
                log.error("socket_listener_stop_failed", error=str(e))
        log.info("daemon_stopped")
        sys.exit(0)


if __name__ == "__main__":
    run()
