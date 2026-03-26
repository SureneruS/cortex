# Team Channels Rules

## tmux vs Channels — separation of concerns

- **Channels for communication.** All inter-session messaging goes through the channels MCP (MongoDB → `<channel>` notifications). Never use `tmux send-keys` to pass messages between team sessions.
- **tmux for terminal management.** Spawning panes, moving windows, killing panes, attaching — all tmux. tmux does process lifecycle; channels does messaging.
- **`cortex session send` is for non-team sessions only.** Team sessions use `send_message` via the channels MCP. Don't mix the two — `send-keys` bypasses the message bus, loses persistence, and Claude can't distinguish it from human typing.

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

## CLI (`cortex team *`)

- **`--task` is the name, `--prompt` is the instructions.** Don't conflate them. Task becomes the slugified session name; prompt is the detailed briefing sent via tmux send-keys after CC starts.
- **Spawn sequence has rollback.** If tmux launch fails after MongoDB registration, mark the session as `dead`.
- **Stale sweep runs on every spawn.** Catches both null `last_seen` (crashed before first heartbeat) and `last_seen > 5min` (crashed after heartbeat started).
- **Name uniqueness is find_one, not atomic.** Accepted v1 limitation at low concurrency. Document if this causes issues.

## Daemon

- **Human message routing polls every 10s**, separate from the 60s cron job cycle. Uses a counter pattern in the main loop.
- **Slack delivery via SlackPoster** with env vars `SLACK_BOT_TOKEN` and `SLACK_TARGET_USER_ID`. Falls back to `~/.cortex/human-messages/` files if Slack is not configured.
- **Atomic claim before Slack delivery.** `find_one_and_update(status: pending → delivered)` prevents double delivery if the daemon restarts mid-cycle.

## Known Constraints

- **Plan mode disabled with `--channels`.** Team sessions cannot enter plan mode or use AskUserQuestion. Plan interactively before enabling channels.
- **No interrupt via channels.** Messages arrive between turns, not mid-turn. Ctrl+C in terminal is the only interrupt.
- **`--dangerously-load-development-channels` required.** Channels are research preview. If the protocol changes, only `ChannelTransport` in the TS MCP needs updating. MongoDB layer is unaffected.
- **Auto mode classifier blocks `send_message`.** Must add `mcp__cortex-team__*` to allowedTools in spawn config.
