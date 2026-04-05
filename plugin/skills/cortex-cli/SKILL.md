---
name: cortex-cli
description: Use when you need to interact with Cortex — logging updates/decisions, managing streams, PR operations, session orchestration, checkpoints, cron jobs, or searching history. Complete CLI reference for all cortex commands.
---

# Cortex CLI Reference

Output defaults to human-friendly Rich format on TTY, JSON when piped (non-TTY). Use `--json` flag to force JSON. CC sessions get JSON automatically since Bash tool output is piped. Errors return `{"error": "..."}` with exit code 1 in JSON mode.

## Streams

Work streams track ongoing features, bugs, and initiatives.

```bash
# List streams (default: active)
cortex stream list [--status active|completed|all]

# Get full context (updates, decisions, sessions)
cortex stream get <stream_id>

# Create
cortex stream create --title "..." --repos repo1,repo2 [--metadata '{}']

# Update fields
cortex stream update <stream_id> [--title "..."] [--status active|completed] [--repos r1,r2] [--summary "..."] [--metadata '{}'] [--replace-metadata]

# Mark completed
cortex stream complete <stream_id> --summary "..."

# Log progress update
cortex stream log <stream_id> --content "..." --summary "..."  [--metadata '{}']

# Log decision
cortex stream decide <stream_id> --what "..." --why "..." [--metadata '{}']

# Edit existing entry
cortex stream edit <entry_id> --type update [--content "..."] [--summary "..."]
cortex stream edit <entry_id> --type decision [--what "..."] [--why "..."]

# Delete
cortex stream delete <entry_id> --type stream|update|decision

# Search across all updates, decisions, checkpoints
cortex stream search "<query>"

# Link session to stream
cortex stream link <session_id> <stream_id> [--repo name] [--branch name]
```

### Logging guidelines
- **Log as you go** — if you make a decision or complete a milestone, log it immediately
- `stream log` for progress: milestones, blockers, phase completions
- `stream decide` for choices: architecture, tradeoffs, "we chose X because Y"
- Check `cortex stream list` at session start for active work context

## Checkpoints

Weekly status snapshots.

```bash
# Save (auto-captures active stream IDs if --stream-ids omitted)
cortex checkpoint save --week 2026-W12 --content "..." [--stream-ids id1,id2] [--metadata '{}']

# Get (latest if --week omitted)
cortex checkpoint get [--week 2026-W12]
```

## PR Operations

GitHub PR monitoring and review management.

```bash
# State summary (CI, reviews, action needed)
cortex pr state <number> [--repo owner/repo]

# Review threads (with thread IDs for resolve)
cortex pr threads <number> [--repo owner/repo]

# CI check details
cortex pr checks <number> [--repo owner/repo]

# React to comment (+1 or -1)
cortex pr react <number> <comment_id> <reaction> [--repo owner/repo]

# Resolve a review thread
cortex pr resolve <thread_id>

# Batch react + resolve
cortex pr batch-resolve --items '[{"comment_id":123,"thread_id":"PRRT_...","reaction":"+1"}]' [--repo owner/repo]

# Reply to comment
cortex pr reply <number> <comment_id> --body "..." [--repo owner/repo]

# Watch PR (registers session for change monitoring)
cortex pr watch <number> <session_id> [--repo owner/repo] [--message "..."]
```

## Sessions

Managed Claude Code worker sessions in tmux panes.

```bash
# Spawn new session
cortex session spawn --name <name> [--goal "..."] [--prompt "..."] [--repo <name>] \
  [--beside <ref>] [--below <ref>] [--color <name>] \
  [--model sonnet] [--permission-mode plan] [--effort high] \
  [--worktree <name>] [--resume <cc-uuid>] [--workspace default|background]

# List (default: active, brief)
cortex session list [--status active|paused|blocked|archived|all] [--limit 20] [--brief]

# Get details
cortex session get <session_id_or_name>

# Update session data
cortex session update <session_id> --data '{"status":"idle"}'

# Send text to session pane
cortex session send <session_id> <text>

# Capture pane output
cortex session capture <session_id> [--lines 50]

# Close session
cortex session close <session_id> [--force]

# Pause (send /exit, preserve cc_session_id for resume)
cortex session pause <session_id_or_name>

# Resume a paused session (spawns with --resume)
cortex session resume <session_id_or_name>

# Hide (move to background workspace, still running)
cortex session hide <session_id_or_name>

# Show (bring back from background)
cortex session show <session_id_or_name>

# Spatial layout (JSON: pane positions, sizes, session mapping)
cortex session layout [--window <name>]

# Paint tmux borders by runtime state (demo)
cortex session paint [<ref>] [--color <name|hex>]

# Gather sessions into one window
cortex session gather <name1> <name2> [<name3>...] [--layout tiled|even-horizontal|even-vertical]

# Scatter panes into separate windows (tabs)
cortex session scatter <name1> <name2> [<name3>...]

# Move a pane beside or below another
cortex session move <name> --beside <other>
cortex session move <name> --below <other>

# Health check (runtime status, pane liveness)
cortex session health
```

### Session spawn notes
- `--goal` is metadata only (shows in list/get)
- `--prompt` is what gets typed into the session
- `--beside`/`--below` resolve by session name, ID prefix, or %pane_id
- `--color` auto-cycles (blue/green/yellow/purple/orange/pink/cyan/red) if omitted
- Don't use both `--prompt` and `session send` — pick one

## Cron Jobs

Persistent scheduled tasks.

```bash
cortex cron create --name <name> --cron "*/5 * * * *" --action check-watches [--args '{}']
cortex cron list
cortex cron delete <name>
cortex cron pause <name>
cortex cron resume <name>
```

## Daemon

Background daemon for cron execution.

```bash
cortex daemon start
cortex daemon stop
cortex daemon status
```

## Other

```bash
cortex status          # Quick view of active streams
cortex brief           # Compact session brief (for hooks)
cortex reindex         # Rebuild vector embedding index
cortex tasks           # Restore pending tasks from last session
```
