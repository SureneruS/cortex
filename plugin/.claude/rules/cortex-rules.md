# Cortex Rules

## Session Orchestration

Sessions are Claude Code instances running in tmux panes, managed by Cortex.

### CLI Commands (not MCP)
- **`cortex session spawn`** — create a new session. Do NOT use the Agent tool, subagents, or `claude -p`.
- **`cortex session list`** — list managed sessions. Do NOT use Claude Code's built-in session list.
- **`cortex session get`** — get session details by ID or name.

### Role Enforcement
Check `CORTEX_SESSION_ROLE` environment variable:
- **`control` or unset** — can spawn, list, manage sessions
- **`worker`** — can spawn sub-workers, list/get, update own status. Global limit: 15 active sessions.

### Session Hierarchy
- Any session can spawn sub-workers via `cortex session spawn`
- Spawned sessions track their parent via `parent_id` and `CORTEX_PARENT_ID` env var
- Only an ancestor or self can close a session (enforced in code)
- Use `cortex session close <ref> --cascade` to close a session and all its descendants
- `cortex session children <ref>` — list direct children
- `cortex session tree` — show full hierarchy

## Logging Discipline

- **Log as you go, not after the fact** — decisions, milestones, blockers get logged immediately
- `cortex stream log` — progress updates, phase completions, blockers
- `cortex stream decide` — architectural choices, tradeoffs, "X because Y"
- Check `cortex stream list` at session start for context
- Never silently ignore errors — if a cortex command fails, investigate and retry

## Stream Lifecycle

- Check active streams at session start: `cortex stream list`
- Link your session to the relevant stream: `cortex stream link`
- Log updates as work progresses
- Complete streams when done: `cortex stream complete`
- Don't store stream IDs in memory — always query at runtime
