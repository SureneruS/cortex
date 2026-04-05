---
name: session-wrapup
description: Use when the user signals end of session — phrases like "let's wrap up", "we're done", "that's it for now", "let's end the session", "done for now", "let's call it", "wrap up and memorize"
---

# Session Wrapup

Automates end-of-session cleanup: memorize insights, update Cortex, clean git, cancel crons.

## Workflow

### 1. Memorize

Invoke `/memorize` to capture session insights to Cortex memory. Wait for it to complete before continuing.

### 2. Knowledge effectiveness review

Get the session ID: `echo $CLAUDE_CODE_SESSION_ID` (set by SessionStart hook). If empty, derive from `ls -t ~/.claude/projects/-Users-suren-workspace-cercli/*.jsonl | head -1`.

Read `~/cortex/sessions/{session_id}/injected.json` to see what knowledge entries were injected at session start. If the file doesn't exist, skip this step.

For each entry, rate:
- **used** — actively influenced a decision or prevented a mistake
- **relevant** — related to the work but didn't change behavior
- **irrelevant** — not related to this session's work

Append ratings to `~/cortex/effectiveness.jsonl` (one JSON line per entry):

```jsonl
{"session_id": "abc123", "entry": "lazy-raise-testing-pattern.md", "title": "...", "rating": "used", "note": "prevented eager loading issue", "timestamp": "2026-03-15T12:00:00Z"}
```

Keep it quick — 30 seconds max. If unsure, rate "relevant" and move on.

### 3. Update Cortex

- `cortex_get_active_streams` — find streams related to this session's work
- `cortex_log_update` — log progress, decisions, or completions on relevant streams
- `cortex_complete_stream` — **only** if stream's work is fully done (PR merged, feature shipped). Most sessions end mid-stream — update, don't complete.

### 4. Git cleanup

Run these checks and clean up where safe:

```bash
git worktree list          # Remove worktrees for merged PRs
git branch -vv             # Delete local branches for merged PRs (branch -D)
git stash list             # Drop stashes related to completed work
git status                 # Warn if uncommitted changes exist
```

**Best-effort only** — warn about uncommitted changes, never force-clean. Ask before deleting anything ambiguous.

### 5. Report tooling issues

Reflect on the session — did you encounter any unexpected tooling behavior? Silent failures, wrong outputs, stale data, workarounds needed? If so, invoke `/report-issue` for each one. This writes to `~/cortex/issues/`.

Then check `~/cortex/issues/` for any issues from today (including ones logged proactively mid-session). Summarize to the user: what was reported, whether it needs follow-up or is informational.

### 6. Cancel active crons

`CronList` → cancel any `/babysit-pr` or `/loop` jobs with `CronDelete`. Crons die with the session anyway, but explicit cleanup is cleaner.

### 7. Confirm

Start with two lines:
- **Achieved:** One sentence summarizing what was accomplished this session
- **Insight:** One actionable takeaway the user should know (a discovery, risk, optimization, or decision that matters beyond this session)

Then report what was cleaned up. Flag anything still pending:
- Open PRs awaiting review
- Uncommitted work
- Active Cortex streams continuing to next session

### 8. Close (worker sessions only)

Check `CORTEX_SESSION_ROLE` environment variable.

**If worker session** (`CORTEX_SESSION_ROLE=worker`):
Run `cortex session close $CORTEX_SESSION_NAME --force` — this updates the registry AND kills the pane in one step.

**If control or interactive session**: Do NOT auto-close. The user will exit manually when ready.
