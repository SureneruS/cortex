---
name: check-watches
description: Use when running as the watcher session to check all watched sessions and wake them up when their trigger conditions are met. Handles alarm timers and PR state changes.
---

# Check Watches

Poll all sessions with `watching` status and wake them up when conditions are met.

**Note:** The preferred automated approach is `cortex_cron_create("watcher", "*/5 * * * *", "check-watches")`. This skill is for manual invocation or reference.

## Workflow

### 1. List watched sessions

Call `cortex_session_list(status="watching")` to get all sessions being watched.

If none found, report "No sessions being watched." and stop.

### 2. Check each session's trigger

Read `watch.type` from the session doc to determine the handler.

#### Type: `alarm`

Session doc has:
```json
{"status": "watching", "watch": {"type": "alarm", "wake_at": "ISO timestamp", "message": "text to send"}}
```

Check: is `wake_at` in the past?
- **Yes**: `cortex_session_send(session_id, watch.message)`, then `cortex_session_update(session_id, {"status": "active"})`.
- **No**: Skip. Report time remaining.

#### Type: `pr`

Session doc has:
```json
{"status": "watching", "watch": {"type": "pr", "repo": "owner/repo", "number": 123, "last_state": {...}}}
```

Use MCP tools to check current state:
```
cortex_pr_state(number, repo)
```

Compare result with `last_state`. Detect changes:
- **CI status changed**: any check changed state
- **New review comments**: comment/review count increased
- **Review decision changed**: none→approved, none→changes_requested, etc.
- **PR state changed**: open→merged, open→closed

If changed:
1. Compose a specific wake-up message (e.g., "CI check 'Ruff' failed", "new review from @kumarnmanoj")
2. `cortex_session_send(session_id, message)` — include "Handle using /babysit-pr <number>"
3. `cortex_session_update(session_id, {"status": "active", "watch": {"type": "pr", "repo": "...", "number": N, "last_state": <new state>}})` — update last_state

If no change: skip.

### 3. Report summary

```
Checked N sessions. Woke: [names]. Still watching: [names].
```

## Important

- Don't make changes to code or files — only read PR state and send messages
- Be concise in wake-up messages
- If a session's pane is dead (send fails), call `cortex_session_cleanup`
