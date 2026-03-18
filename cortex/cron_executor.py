"""Cron executor — polls MongoDB for due jobs and executes them."""

from __future__ import annotations

import json
import subprocess
import time

import structlog

from cortex.observability import setup_logging

setup_logging("daemon")
log = structlog.get_logger("cortex.daemon")

POLL_INTERVAL = 60


def execute_check_watches(job: dict) -> None:
    from cortex import github
    from cortex.session_registry import MongoSessionRepo
    from cortex.mongo import get_db

    db = get_db()
    session_repo = MongoSessionRepo(db)

    sessions = session_repo.list({"status": "watching"})
    if not sessions:
        log.info("No sessions watching")
        return

    for session in sessions:
        watch = session.get("watch", {})
        if watch.get("type") != "pr":
            if watch.get("type") == "alarm":
                from datetime import datetime, timezone

                wake_at = datetime.fromisoformat(watch["wake_at"])
                if wake_at <= datetime.now(timezone.utc):
                    log.info("Alarm triggered for session %s", session["_id"])
                    subprocess.run(
                        [
                            "cortex",
                            "session",
                            "send",
                            session["_id"],
                            watch.get("message", "Alarm triggered"),
                        ],
                        capture_output=True,
                    )
                    session_repo.update(session["_id"], {"status": "active"}, trigger="cron")
            continue

        repo = watch.get("repo")
        number = watch.get("number")
        last_state = watch.get("last_state", {})

        if not repo or not number:
            log.warning("Session %s has incomplete watch data", session["_id"])
            continue

        try:
            current_state = github.pr_state(number, repo)
        except Exception as e:
            log.error("Failed to fetch PR state for %s#%s: %s", repo, number, e)
            continue

        if current_state == last_state:
            log.info("No changes for %s#%s (session %s)", repo, number, session["name"])
            continue

        changes = []
        if current_state.get("state") != last_state.get("state"):
            changes.append(f"PR state: {last_state.get('state')} -> {current_state.get('state')}")
        if current_state.get("reviewDecision") != last_state.get("reviewDecision"):
            changes.append(
                f"Review: {last_state.get('reviewDecision')} -> {current_state.get('reviewDecision')}"
            )
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

        if not changes:
            log.info("Minor state diff for %s#%s, updating baseline", repo, number)
            session_repo.update(
                session["_id"], {"watch": {**watch, "last_state": current_state}}, trigger="cron"
            )
            continue

        change_summary = "; ".join(changes)
        log.info("Changes detected for %s#%s: %s", repo, number, change_summary)

        custom_message = watch.get("message")
        if custom_message:
            message = f"{custom_message}\n\nContext: PR #{number} on {repo} changed — {change_summary}"
        else:
            prompt = f"""PR #{number} on {repo} has changes:
{change_summary}

Old state: {json.dumps(last_state, indent=2)}
New state: {json.dumps(current_state, indent=2)}

Compose a brief, specific wake-up message for the worker session. End with "Handle using /babysit-pr {number}".
Output ONLY the message text, nothing else."""

            try:
                result = subprocess.run(
                    ["claude", "-p", "--model", "haiku", prompt],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                message = (
                    result.stdout.strip()
                    if result.returncode == 0
                    else f"PR #{number} changed: {change_summary}. Handle using /babysit-pr {number}"
                )
            except (subprocess.TimeoutExpired, Exception):
                message = f"PR #{number} changed: {change_summary}. Handle using /babysit-pr {number}"

        log.info("Waking session %s: %s", session["name"], message[:100])
        subprocess.run(
            ["cortex", "session", "send", session["_id"], message],
            capture_output=True,
        )

        session_repo.update(
            session["_id"],
            {
                "status": "active",
                "watch": {**watch, "last_state": current_state},
            },
            trigger="cron",
        )


def execute_command(job: dict) -> None:
    args = job.get("action_args", {})
    command = args.get("command")
    if not command:
        log.error("Command action missing 'command' in action_args")
        return
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=60)
        log.info("Command '%s' exited %d: %s", command, result.returncode, result.stdout[:200])
    except subprocess.TimeoutExpired:
        log.error("Command '%s' timed out", command)


EXECUTORS = {
    "check-watches": execute_check_watches,
    "command": execute_command,
}


def run() -> None:
    from cortex.cron import CronManager
    from cortex.mongo import get_db

    log.info("Cortex daemon starting (poll interval: %ds)", POLL_INTERVAL)
    db = get_db()
    cron = CronManager(db)

    from cortex.session_registry import MongoSessionRepo, _new_id

    session_repo = MongoSessionRepo(db)
    daemon_id = _new_id()
    session_repo.register(
        daemon_id,
        {
            "name": "cortex-daemon",
            "role": "daemon",
            "goal": "Background cron executor — polls and executes scheduled jobs",
            "status": "active",
        },
    )
    log.info("Registered in session registry: %s", daemon_id)

    while True:
        try:
            due = cron.get_due_jobs()
            if due:
                log.info("Found %d due job(s)", len(due))
            for job in due:
                action = job["action"]
                executor = EXECUTORS.get(action)
                if not executor:
                    log.error("Unknown action type: %s", action)
                    cron.mark_run(job["name"])
                    continue
                try:
                    log.info("Executing job '%s' (action: %s)", job["name"], action)
                    executor(job)
                except Exception as e:
                    log.error("Job '%s' failed: %s", job["name"], e)
                cron.mark_run(job["name"])
        except Exception as e:
            log.error("Daemon loop error: %s", e)

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    run()
