---
name: babysit-pr
description: Use when a PR is open and the user wants autonomous monitoring — handles CI failures, bot comments, human review comments, and merging when ready.
---

# Babysit PR

Monitor an open PR, handle feedback autonomously, and merge when all checks pass.

## Setup

**Watcher mode (preferred):** Register for watching via CLI. The cron watcher will wake you up when something changes:
```bash
cortex pr watch cercli/<repo>#<number> <your-session-id>
```
When woken up, handle the change using this skill's workflow below.

**Self-loop:** Invoke via `/loop 15m /babysit-pr <number>` to poll directly.

## Workflow

### 1. Gather PR state

Use MCP tools — do NOT use `gh` bash commands:
```
cortex_pr_state(number, repo)       # state, CI, reviews, counts
cortex_pr_threads(number, repo)     # all review threads with IDs
cortex_pr_checks(number, repo)      # detailed CI check info
```

### 2. Handle CI failures

Read failed check logs via Bash, fix the issue, push:
```bash
gh run view <run-id> --log-failed
```

### 3. Handle bot comments

Bot comments are automated lint/style checks (propel-bot, claude-bot, etc.):
- **Correct** (real issue): react thumbs up, make code fix, push, resolve thread
- **False positive**: react thumbs down, resolve thread. No code change needed
- **Do NOT reply** to bot comments — just react and resolve

Use MCP tools for reactions and resolving:
```
cortex_pr_react(number, comment_id, "+1", repo)    # or "-1"
cortex_pr_resolve(thread_id)
```

For multiple bot comments, use batch:
```
cortex_pr_batch_resolve(items=[
  {"comment_id": 123, "thread_id": "PRRT_xxx", "reaction": "-1"},
  {"comment_id": 456, "thread_id": "PRRT_yyy", "reaction": "+1"}
], repo="cercli/repo")
```

### 4. Handle human review comments

**Do NOT resolve human reviewer threads** — let the reviewer verify the fix and resolve themselves.

- **Trivial** (typos, naming, style, small refactors): fix, push, and reply:
  ```
  cortex_pr_reply(number, comment_id, "Fixed — <description>", repo)
  ```
  When all addressed, `@` the reviewer: "addressed the comments, please take a look"
- **Non-trivial** (design disagreements, architectural pushback, ambiguous intent): prepare draft reply and/or code changes, then **immediately send Arc DM** to get user's attention. Do NOT reply or push without approval
- **When in doubt (even 1%)**: treat as non-trivial — wait for user

**CRITICAL: Arc DM is mandatory.** When human review comments are found, notify Suren via `mcp__arc__send_message`. For trivial: DM after fixing. For non-trivial: DM immediately.

### 5. Merge criteria

ALL must be true:
- All CI checks green
- All bot comments reacted to and resolved
- All human review comments addressed or resolved
- `reviewDecision` shows `APPROVED`

When all met: squash-merge the PR, then send Arc DM confirming.
```bash
gh pr merge <number> --squash
```

### 6. Watch persistence

The PR watch is **persistent** — the daemon automatically updates the baseline after each wake and keeps watching until the PR is merged or closed. No manual re-registration needed.

If you need to stop watching early (e.g., PR abandoned), the watch clears automatically when the PR state is no longer OPEN.
