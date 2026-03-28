# Cortex Tutorial

A hands-on guide to Cortex — from first run to multi-session orchestration.

Each chapter builds on the previous. Follow along in order, or jump to the section you need.

---

## Table of Contents

1. [Getting Started](#1-getting-started)
2. [Streams — Tracking Your Work](#2-streams--tracking-your-work)
3. [Sessions — Spawning Workers](#3-sessions--spawning-workers)
4. [Channels — Inter-Session Messaging](#4-channels--inter-session-messaging)
5. [Session Lifecycle — Pause, Resume, Hide, Show](#5-session-lifecycle--pause-resume-hide-show)
6. [Spatial Layout — Gather, Scatter, Move](#6-spatial-layout--gather-scatter-move)
7. [Session Close — Graceful Wrapup](#7-session-close--graceful-wrapup)
8. [Health & Monitoring](#8-health--monitoring)
9. [PR Operations](#9-pr-operations)
10. [Cron Jobs & Daemon](#10-cron-jobs--daemon)
11. [Checkpoints — Weekly Snapshots](#11-checkpoints--weekly-snapshots)
12. [Search — Finding Past Context](#12-search--finding-past-context)
13. [Dashboard & UI](#13-dashboard--ui)
14. [Advanced Patterns](#14-advanced-patterns)

---

## 1. Getting Started

### Prerequisites

- Python 3.11+, uv, MongoDB running locally
- tmux (all sessions run in tmux panes)
- Claude Code CLI (`claude`) installed
- Fish shell (for session shell commands)

### Install

```fish
# From the cortex repo
uv tool install --editable . --force
```

### Initialize

```fish
cortex init
```

This scans your repos, creates the MongoDB database, and sets up the config at `~/.cortex/config.json`.

### Verify

```fish
cortex status
```

Shows active streams. If this is your first run, you'll see an empty list.

---

## 2. Streams — Tracking Your Work

Streams are the backbone of Cortex's context system. A stream represents a unit of work (feature, bugfix, investigation) and accumulates updates and decisions over time.

### Create a stream

```fish
cortex stream create --title "Add user search API" --repos recruitment-backend
```

Returns a stream ID (e.g., `a1b2c3d4e5f6`). You'll use this ID for all subsequent operations.

### Log progress updates

```fish
cortex stream log <stream_id> --content "Implemented the search endpoint" --summary "Search endpoint done"
```

### Log architectural decisions

```fish
cortex stream decide <stream_id> --what "Use PostgreSQL full-text search" --why "Simpler than Elasticsearch for our scale"
```

### View stream context

```fish
cortex stream get <stream_id>
```

Shows the full stream with all updates, decisions, and linked sessions.

### List active streams

```fish
cortex stream list
```

### Complete a stream

```fish
cortex stream complete <stream_id>
```

### Try it yourself

> 1. Create a stream for something you're working on
> 2. Log 2-3 updates as you make progress
> 3. Log a decision explaining a tradeoff you made
> 4. Run `cortex stream get <id>` to see the full context

---

## 3. Sessions — Spawning Workers

Sessions are Claude Code instances running in tmux panes, managed by Cortex. Every session gets channels MCP for inter-session messaging.

### Spawn a basic session

```fish
cortex session spawn --name my-worker --goal "Fix the login bug"
```

This creates a tmux pane with Claude Code running, registered in the Cortex session registry.

### Spawn with an initial prompt

```fish
cortex session spawn --name api-fixer --prompt "Fix the N+1 query in /api/users" --repo recruitment-backend
```

The prompt is delivered via the channels message bus once Claude Code connects.

### Spawn in a specific repo

```fish
cortex session spawn --name frontend-worker --repo frontend
```

### Spawn with a specific model

```fish
cortex session spawn --name quick-task --model haiku
```

### Spawn beside another session (spatial)

```fish
cortex session spawn --name helper --beside api-fixer
```

Creates a horizontal split next to the `api-fixer` pane.

```fish
cortex session spawn --name debugger --below api-fixer
```

Creates a vertical split below it.

### Spawn in the background

```fish
cortex session spawn --name bg-task --workspace background --prompt "Run the full test suite"
```

Background sessions live in a separate tmux session, out of your main view.

### List sessions

```fish
cortex session list
```

```fish
# Filter by status
cortex session list --status active

# Brief mode (no events)
cortex session list --brief
```

### Get session details

```fish
cortex session get my-worker
```

### Capture pane output

```fish
cortex session capture my-worker --lines 100
```

### Link a session to a stream

```fish
cortex link <session_id> <stream_id>
```

### Try it yourself

> 1. Spawn a session: `cortex session spawn --name tutorial-test --goal "Test session"`
> 2. List sessions: `cortex session list --brief`
> 3. Capture output: `cortex session capture tutorial-test`
> 4. Attach to it: `cortex session attach tutorial-test`

---

## 4. Channels — Inter-Session Messaging

All sessions communicate through the channels MCP — a MongoDB-backed message bus with automatic delivery.

### Send a message to a session

```fish
cortex session message <session-name> "Hey, can you check the API response format?"
```

The message is written to MongoDB as `pending` and the target session's channels MCP polls and delivers it as a `<channel>` notification into Claude's context.

### Send a message to the human (Slack)

Sessions can send messages to `"human"` which routes through the daemon to Slack:

```
# Inside a Claude session (via send_message MCP tool):
send_message(to="human", content="I found a bug in the auth flow, need your input")
```

### View message history

```fish
# All messages
cortex session messages

# Messages for a specific session
cortex session messages my-worker

# Messages to human
cortex session messages --to human
```

### How delivery works

1. Sender writes message to MongoDB (`status: "pending"`)
2. Recipient's channels MCP polls every 1.5s
3. Atomic `findOneAndUpdate` claims the message (`pending → delivered`)
4. MCP emits `notifications/claude/channel` into Claude's context
5. Claude sees it as a `<channel from="sender" type="request">` notification

### Message types

| Type | Use for |
|---|---|
| `request` | Asking another session to do something |
| `notification` | FYI updates |
| `status_update` | Progress reports |
| `handoff` | Transferring work to another session |
| `lifecycle` | System messages (wrapup, shutdown) |

### Try it yourself

> 1. Spawn two sessions: `cortex session spawn --name alice` and `cortex session spawn --name bob`
> 2. Send a message: `cortex session message alice "Hello from the CLI"`
> 3. Check message history: `cortex session messages alice`
> 4. From inside Alice's session, use `send_message(to="bob", content="Hi Bob!")` via the MCP tool

---

## 5. Session Lifecycle — Pause, Resume, Hide, Show

### Pause a session

Sends `/exit` to Claude Code, preserves the CC session ID for later resume.

```fish
cortex session pause my-worker
```

### Resume a paused session

Spawns a new pane with `--resume` pointing to the saved CC session ID.

```fish
cortex session resume my-worker
```

### Restart a session (pause + resume)

Useful when upgrading Claude Code or clearing a stuck session.

```fish
cortex session restart my-worker
```

### Hide a session (background)

Moves the pane to the background tmux session — still running, just out of sight.

```fish
cortex session hide my-worker
```

### Show a hidden session

Brings it back to your main workspace.

```fish
cortex session show my-worker
```

### Try it yourself

> 1. Spawn a session: `cortex session spawn --name lifecycle-test`
> 2. Hide it: `cortex session hide lifecycle-test`
> 3. List sessions — it should show status `hidden`: `cortex session list --brief`
> 4. Show it: `cortex session show lifecycle-test`
> 5. Pause it: `cortex session pause lifecycle-test`
> 6. Resume it: `cortex session resume lifecycle-test`

---

## 6. Spatial Layout — Gather, Scatter, Move

Control how session panes are arranged in tmux.

### Gather sessions into one window

Merges multiple session panes into a single tmux window with a layout.

```fish
cortex session gather session-a session-b session-c --layout tiled
```

Available layouts: `tiled`, `even-horizontal`, `even-vertical`, `main-horizontal`, `main-vertical`

### Scatter sessions into separate windows

The reverse of gather — breaks panes back into individual tabs.

```fish
cortex session scatter session-a session-b session-c
```

### Move a session beside/below another

```fish
cortex session move helper --beside main-worker
cortex session move debugger --below main-worker
```

### View the spatial layout

```fish
cortex session layout
```

Shows all windows, panes, their positions, sizes, and mapped session names.

```fish
# Filter to a specific window
cortex session layout --window 0
```

### Paint pane borders by runtime state

```fish
# Paint all sessions by their runtime state (working=green, waiting=amber)
cortex session paint

# Paint a specific session
cortex session paint my-worker --color blue
```

### Try it yourself

> 1. Spawn 3 sessions: `cortex session spawn --name a`, `--name b`, `--name c`
> 2. Gather them: `cortex session gather a b c --layout tiled`
> 3. View layout: `cortex session layout`
> 4. Scatter them: `cortex session scatter a b c`

---

## 7. Session Close — Graceful Wrapup

Close uses a channels-first approach with tmux fallback.

### Happy path (channels)

```fish
cortex session close my-worker
```

1. Sends a "wrapup" message via channels to the session
2. Waits up to 30s for the session to acknowledge and wrap up
3. If the session completes: expires pending messages, closes registry, cleans up pane
4. If the session doesn't respond: falls back to tmux `/session-wrapup` via send-keys
5. If that also times out: kills the pane

### Force close

Skips wrapup entirely — expires messages, kills pane immediately.

```fish
cortex session close --force my-worker
```

### Bulk cleanup

Finds all sessions with dead tmux panes and marks them as dead.

```fish
cortex session cleanup
```

### Try it yourself

> 1. Spawn a session: `cortex session spawn --name close-test`
> 2. Close it gracefully: `cortex session close close-test`
> 3. Check it's gone: `cortex session list --brief`

---

## 8. Health & Monitoring

### Health check

Comprehensive scan of all sessions — finds dead panes, stale sessions, untracked panes, and runtime state.

```fish
cortex session health
```

Returns structured JSON with severity levels (`critical`, `warning`, `info`). Automatically marks dead-pane sessions as dead and updates runtime state.

### What it checks

| Check | Severity | Action |
|---|---|---|
| Session has no live tmux pane | Critical | Auto-marks as dead |
| Session idle >24h | Warning | Flagged for review |
| tmux pane not in session registry | Info | Reported as untracked |
| Session runtime state | Info | Updated (working/waiting_input) |

### Session brief (for hooks)

```fish
cortex brief
```

Returns a compact summary of active sessions for injection into Claude's context via hooks.

### Try it yourself

> 1. Run health check: `cortex session health`
> 2. Look at the findings — any stale or dead sessions?
> 3. Clean up: `cortex session cleanup`

---

## 9. PR Operations

Cortex wraps GitHub PR operations for use from Claude Code sessions.

### Get PR state

```fish
cortex pr state 123 --repo recruitment-backend
```

Returns: status, CI checks, review decision, mergeable state.

### List review threads

```fish
cortex pr threads 123 --repo recruitment-backend
```

### Reply to a review comment

```fish
cortex pr reply 123 --repo recruitment-backend --comment-id 12345 --body "Fixed in latest push"
```

### React to comments

```fish
cortex pr react 123 --repo recruitment-backend --comment-id 12345 --reaction "+1"
```

### Resolve a thread

```fish
cortex pr resolve 123 --repo recruitment-backend --thread-id abc123
```

### Batch resolve

```fish
cortex pr batch-resolve 123 --repo recruitment-backend --thread-ids "id1,id2,id3"
```

### Watch a PR (session monitors for changes)

```fish
cortex pr watch 123 --repo recruitment-backend
```

Registers the current session to watch the PR. Used by the `check-watches` cron job.

### Get CI check details

```fish
cortex pr checks 123 --repo recruitment-backend
```

---

## 10. Cron Jobs & Daemon

The Cortex daemon runs persistent background tasks.

### Start the daemon

```fish
cortex daemon start
```

Launches the daemon in a dedicated tmux session (`cortex-daemon`).

### Check daemon status

```fish
cortex daemon status
```

### Create a cron job

```fish
cortex cron create --name "check-watches" --schedule "*/5 * * * *" --command "check_watches"
```

### List cron jobs

```fish
cortex cron list
```

### Pause/resume a cron job

```fish
cortex cron pause <job_id>
cortex cron resume <job_id>
```

### Delete a cron job

```fish
cortex cron delete <job_id>
```

### What the daemon does

- **Cron executor**: runs due cron jobs on schedule
- **Human message routing**: polls for `send_message(to="human")` every 10s, delivers via Slack
- **Stale session detection**: flags sessions that haven't heartbeated

---

## 11. Checkpoints — Weekly Snapshots

Checkpoints capture the state of the world at a point in time — useful for weekly planning.

### Save a checkpoint

```fish
cortex checkpoint save --week "2026-W13" --data '{"summary": "Shipped auth migration", "carry_over": ["ATS-456"]}'
```

### Get the latest checkpoint

```fish
cortex checkpoint get
```

### Get a specific week

```fish
cortex checkpoint get --week "2026-W13"
```

---

## 12. Search — Finding Past Context

Search across all updates, decisions, and checkpoints using text and vector similarity.

### Text search

```fish
cortex stream search "permission migration"
```

### The search covers

- Stream updates (progress logs)
- Decisions (architectural choices)
- Checkpoints (weekly snapshots)

Results are ranked by relevance using both text matching and vector embeddings.

---

## 13. Dashboard & UI

### TUI Dashboard

```fish
cortex dashboard
```

Opens an interactive terminal UI (Textual) showing streams, sessions, and activity.

### Web UI

```fish
cortex ui
```

Opens the web-based dashboard (FastAPI + SSE for real-time updates).

---

## 14. Advanced Patterns

### Multi-session workflow

```fish
# Spawn workers for parallel tasks
cortex session spawn --name backend-fix --repo recruitment-backend --prompt "Fix the N+1 in job listing"
cortex session spawn --name frontend-fix --repo frontend --prompt "Update the job list component to handle pagination"

# Monitor from control session
cortex session messages

# Send coordination messages
cortex session message backend-fix "Frontend is done, make sure the API response matches the expected shape"
```

### Session-to-stream linking

```fish
# Create a stream for the feature
cortex stream create --title "Job listing performance" --repos recruitment-backend,frontend

# Spawn a session and link it
cortex session spawn --name perf-worker --repo recruitment-backend
cortex link <session_id> <stream_id>
```

Updates logged by the session appear in the stream context.

### Close with wrapup chain

When closing a session that's actively working:

1. `cortex session close worker-1` sends wrapup message via channels
2. Worker receives the lifecycle message, runs `/session-wrapup` to save learnings
3. Worker updates its status to `completed` and exits
4. Cortex expires pending messages and closes the registry entry

If the session is unresponsive, Cortex falls back to tmux send-keys, then kills the pane.

### Background tasks

```fish
# Run a long task in the background
cortex session spawn --name test-runner --workspace background --prompt "Run the full E2E test suite and report results via send_message(to='human')"
```

Background sessions are invisible but still registered and monitored.

### Session status via hooks

The `SessionStart` hook (`cortex-hook-session-start`) automatically:
- Registers the session in MongoDB
- Injects active streams and session context into Claude's system prompt
- Sets up CORTEX_SESSION_ID for self-identification

---

## Quick Reference

| Command | What it does |
|---|---|
| `cortex init` | Initialize Cortex |
| `cortex status` | Show active streams |
| `cortex stream create` | Start tracking work |
| `cortex stream log` | Log progress |
| `cortex stream decide` | Log a decision |
| `cortex session spawn` | Create a new Claude Code session |
| `cortex session list` | List all sessions |
| `cortex session message` | Send a message to a session |
| `cortex session messages` | View message history |
| `cortex session attach` | Jump to a session's pane |
| `cortex session close` | Gracefully close a session |
| `cortex session health` | Check session health |
| `cortex session gather` | Merge panes into one window |
| `cortex session scatter` | Split panes into separate windows |
| `cortex pr state` | Get PR status |
| `cortex cron list` | List cron jobs |
| `cortex checkpoint save` | Save weekly snapshot |
| `cortex stream search` | Search past context |
