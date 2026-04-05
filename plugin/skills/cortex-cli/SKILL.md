---
name: cortex-cli
description: Use when you need to interact with Cortex — logging updates/decisions, managing streams, PR operations, session orchestration, checkpoints, cron jobs, or searching history. Complete CLI reference for all cortex commands.
---

# Cortex CLI Reference

Output defaults to human-friendly Rich format on TTY, JSON when piped (non-TTY). Use `--json` flag to force JSON. CC sessions get JSON automatically since Bash tool output is piped. Errors return `{"error": "..."}` with exit code 1 in JSON mode.

<!-- AUTO-START -->

## Streams

Manage work streams, updates, and decisions.

```bash
# Mark a stream as completed.
cortex stream complete <ref> --summary

# Create a new stream.
cortex stream create --title --repos [--metadata]

# Log a decision to a stream.
cortex stream decide <ref> --what --why [--metadata]

# Delete a stream, update, or decision.
cortex stream delete <entry_id> --type stream|update|decision

# Edit an existing update or decision.
cortex stream edit <entry_id> --type update|decision [--content] [--summary] [--what] [--why] [--metadata]

# Get full stream context (updates, decisions, sessions).
cortex stream get <ref>

# Link a session to a stream.
cortex stream link <session_id> <stream_ref> [--repo] [--branch]

# List streams.
cortex stream list [--status]

# Log a progress update to a stream.
cortex stream log <ref> --content --summary [--metadata]

# Search across updates, decisions, and checkpoints.
cortex stream search <query>

# Update a stream.
cortex stream update <ref> [--title] [--status] [--repos] [--summary] [--metadata] [--replace-metadata]
```

### Logging guidelines
- **Log as you go** — if you make a decision or complete a milestone, log it immediately
- `stream log` for progress: milestones, blockers, phase completions
- `stream decide` for choices: architecture, tradeoffs, "we chose X because Y"
- Check `cortex stream list` at session start for active work context

## Checkpoints

Manage weekly checkpoints.

```bash
# Get a checkpoint (latest or specific week).
cortex checkpoint get [--week]

# Save or update a weekly checkpoint.
cortex checkpoint save --week --content [--stream-ids] [--metadata]
```

## PR Operations

GitHub PR operations.

```bash
# React to and resolve multiple PR threads.
cortex pr batch-resolve --items [--repo]

# Get CI check details for a PR.
cortex pr checks <number> [--repo]

# React to a PR review comment (+1 or -1).
cortex pr react <number> <comment_id> <reaction> [--repo]

# Reply to a PR review comment.
cortex pr reply <number> <comment_id> --body [--repo]

# Resolve a PR review thread.
cortex pr resolve <thread_id>

# Get PR state summary.
cortex pr state <number> [--repo]

# List PR review threads.
cortex pr threads <number> [--repo]

# Register a session to watch a PR for changes.
cortex pr watch <pr_ref> [SESSION_ID] [--message]

# List all active PR watches.
cortex pr watches
```

## Sessions

Manage Claude Code sessions.

```bash
# Jump to a session's tmux pane.
cortex session attach <session_id>

# Capture terminal output from a session's tmux pane.
cortex session capture <session_id> [--lines INTEGER]

# List direct child sessions spawned by a session.
cortex session children <ref> [--all]

# Close all active sessions with dead tmux panes.
cortex session cleanup

# Close a session — expire messages, update registry, signal exit.
cortex session close <session_id> [--force] [--cascade]

# Gather sessions into a single window with a layout.
cortex session gather REFS... [--layout]

# Get a session by ID, name, or ID prefix.
cortex session get <session_id>

# Comprehensive health check.
cortex session health

# Move a session to the background workspace.
cortex session hide <session_id>

# Show spatial layout of all panes with session mappings.
cortex session layout [--window]

# Link a new CC session ID (appends to cc_sessions array).
cortex session link-cc <session_id> <cc_session_id> [--data]

# List registered sessions. Shows non-terminal sessions by default.
cortex session list [--status] [--runtime] [--all] [--brief] [--limit INTEGER]

# Send a message to a session via channels.
cortex session message <session_name> <content> [--thread-id] [--meta]

# View recent inter-session messages.
cortex session messages [SESSION_NAME] [--to] [--limit INTEGER]

# Move a session's pane beside or below another session.
cortex session move <ref> [--beside] [--below]

# Pause a session — sends /exit, preserves cc_session_id for resume.
cortex session pause <session_id>

# Restart CC — pause then resume with new CC version.
cortex session restart <session_id>

# Resume a paused session.
cortex session resume <session_id>

# Break sessions into separate windows (tabs).
cortex session scatter REFS...

# Bring a hidden session back from background.
cortex session show <session_id>

# Spawn a new Claude Code session in a tmux pane.
cortex session spawn --name [--goal] [--prompt] [--workspace] [--model] [--split] [--resume] [--repo] [--permission-mode] [--effort] [--agent] [--allowed-tools] [--worktree] [--beside] [--below] [--color]

# Show session hierarchy as a tree.
cortex session tree [REF]

# Update a session's fields.
cortex session update <session_id> --data [--trigger] [--increment]

# Live-tail messages between sessions in a chat view.
cortex session watch [NAMES] [--limit INTEGER] [--poll FLOAT] [--no-live] [--mode messages|full|interactive]

# Run wrapup routine on a session (memorize, save tasks, etc.).
cortex session wrapup <session_id>
```

### Session spawn notes
- `--goal` is metadata only (shows in list/get)
- `--prompt` is what gets typed into the session via channels
- `--beside`/`--below` resolve by session name, ID prefix, or %pane_id
- `--color` auto-cycles (blue/green/yellow/purple/orange/pink/cyan/red) if omitted
- Don't use both `--prompt` and `session message` — pick one

## Cron Jobs

Manage persistent cron jobs.

```bash
# Create a cron job.
cortex cron create --name --cron --action [--args]

# Delete a cron job.
cortex cron delete <name>

# List all cron jobs.
cortex cron list

# Pause a cron job.
cortex cron pause <name>

# Resume a paused cron job.
cortex cron resume <name>
```

## Daemon

Manage the Cortex background daemon.

```bash
# Clean up stale daemon data: legacy logs, debug log bloat, orphan registry entries.
cortex daemon cleanup [--dry-run]

# View daemon logs in a human-readable format.
cortex daemon logs [-n INTEGER] [-f] [--level debug|info|warning|error] [--debug]

# Start the daemon as a launchd service (auto-restarts on crash, starts on login).
cortex daemon start

# Check if the daemon is running.
cortex daemon status

# Stop the daemon.
cortex daemon stop
```

## Testing

Run E2E test suites.

```bash
# List available test suites.
cortex test list

# Run a test suite with pre-flight checks.
cortex test run <suite> [-v] [-k]

# Generate a smoke test checklist for manual verification.
cortex test smoke <suite>
```

## Other

```bash
# Print compact session brief (for hook injection).
cortex brief

# Open the control session — spawns or reattaches to the single control pane.
cortex control

# Launch the Textual TUI dashboard.
cortex dashboard

# Initialize Cortex: create config, DB, and scan repos for context.
cortex init

# Link a session to a stream.
cortex link <session_id> <stream_ref>

# View aggregated logs from all Cortex components.
cortex logs [-n INTEGER] [-f] [--level CHOICE]

# Rebuild vector embedding index.
cortex reindex

# Show active Cortex streams.
cortex status

# Print pending task backups for session restore.
cortex tasks [--session-id]

# Open the Cortex web UI.
cortex ui [--dev] [--port INTEGER]
```

<!-- AUTO-END -->
