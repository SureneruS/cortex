# Channels Rules

## tmux vs Channels — separation of concerns

- **Channels for ALL communication.** All inter-session messaging — including spawn prompts — goes through channels (MongoDB → `<channel>` notifications). Never use `tmux send-keys` to deliver messages or prompts.
- **tmux for internal terminal control ONLY.** Spawning panes, moving windows, killing panes, env setup, slash commands (/color, /exit, /session-wrapup) — all tmux. tmux does process lifecycle and terminal control; channels does messaging. `send_text` and `send_keys` must never carry user-facing content.
- **All sessions have channels.** Every session spawned via `cortex session spawn` gets the channels MCP. There is no separate "team session" concept — all sessions are peers in the message bus.

## Architecture

- **TS MCP is the only CC-touching component.** The TypeScript channels MCP at `src/channels-mcp/` handles all Claude Code channel protocol communication. Python never emits channel notifications — the Python SDK can't send custom notification methods.
- **Python and TypeScript communicate only via MongoDB.** No cross-language API calls, no shelling out between them. The `messages` collection is the shared bus.
- **All IDs are strings, not ObjectIds.** Critical for cross-driver (pymongo + mongodb native) compatibility. Never use `ObjectId()` in shared collections.
- **Write-first ordering.** Always write to MongoDB (`status: "pending"`) before any delivery attempt. Never deliver without a persistent record. This prevents message loss.

## Message Schema

- **`from` exists at two levels.** Top-level in the MongoDB document (for query efficiency) AND copied into channel notification meta attributes at delivery time. The document is the source of truth.
- **`"human"` is a reserved `to` value.** Bypasses session registry validation. Daemon polls for these and delivers via Slack.
- **`"expired"` status for cancelled messages**, not `"delivered"`. Use when killing sessions or sweeping stale ones — distinguishes "reached recipient" from "cancelled."
- **10KB content limit.** For larger payloads, write to shared memory or a file and send the path.
- **Meta keys: letters, digits, underscores only.** CC silently drops hyphens. Validate before emitting.

## MCP Server (`src/channels-mcp/`)

- **Delivery runs inside `mcp.oninitialized` callback.** Never emit `notifications/claude/channel` before the MCP handshake completes — notifications without a transport silently fail while `findOneAndUpdate` has already claimed the message as delivered. Permanent message loss.
- **setTimeout recursion for polling, not setInterval.** Prevents overlapping polls when MongoDB is slow.
- **Poll limit: 10 messages per cycle.** Prevents context flooding from message storms.
- **Deduplication is two-layer.** Atomic `findOneAndUpdate` (status: pending → delivered) prevents cross-process duplication. In-process `Set<string>` prevents within-process duplication after context compaction recovery.
- **`get_messages` returns sent AND received.** Intentional — enables context recovery after CC compacts older `<channel>` notifications.
- **System prompt via MCP `instructions` field.** Not CLAUDE.md, not hooks, not spawn flags. The instructions field is automatically loaded when the MCP connects.

## CLI (`cortex session *`)

- **`--name` is the session name, `--goal` is metadata, `--prompt` is the initial task.** Prompt is delivered via channels with a readiness gate: Python waits for `channel_status="ready"` (set by MCP on `oninitialized`), writes the message to MongoDB, waits for a reply to confirm delivery, and auto-resends if no reply within 15s.
- **Spawn sequence has rollback.** If tmux launch fails after MongoDB registration, mark the session as `dead`.
- **Stale sweep runs on every spawn.** Catches both null `last_seen` (crashed before first heartbeat) and `last_seen > 5min` (crashed after heartbeat started).
- **Name uniqueness is find_one, not atomic.** Accepted v1 limitation at low concurrency. Document if this causes issues.
- **`cortex team` is deprecated.** Hidden aliases redirect to session equivalents. Use `cortex session spawn/message/messages/close/attach`.

## Daemon

- **Human message routing polls every 10s**, separate from the 60s cron job cycle. Uses a counter pattern in the main loop.
- **Slack delivery via SlackPoster** with env vars `SLACK_BOT_TOKEN` and `SLACK_TARGET_USER_ID`. Falls back to `~/.cortex/human-messages/` files if Slack is not configured.
- **Atomic claim before Slack delivery.** `find_one_and_update(status: pending → delivered)` prevents double delivery if the daemon restarts mid-cycle.

## Known Constraints

- **Plan mode disabled with `--channels`.** Sessions with channels cannot enter plan mode or use AskUserQuestion. Plan interactively before enabling channels.
- **No interrupt via channels.** Messages arrive between turns, not mid-turn. Ctrl+C in terminal is the only interrupt.
- **`--dangerously-load-development-channels` required.** Channels are research preview. All sessions spawned via `cortex session spawn` include this flag. If the protocol changes, only `ChannelTransport` in the TS MCP needs updating. MongoDB layer is unaffected.
- **Auto mode classifier blocks `send_message`.** Must add `mcp__cortex-team__*` to allowedTools in spawn config.
