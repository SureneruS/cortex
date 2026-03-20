---
name: spawn
description: Use when the user asks to spawn, create, or start a new worker session — guides through interactive session creation with name, goal, and workspace.
---

# Spawn Session

Create a new Cortex-managed Claude Code worker session in a tmux pane.

## Workflow

1. Parse the invocation for pre-filled values:
   - `/spawn` — interactive, ask for name and goal
   - `/spawn fix auth bug` — use as goal, generate name from it
   - `/spawn --name worker-1 --goal "fix the auth bug"` — use both directly

2. If name is missing, generate a short kebab-case name from the goal (e.g., "fix auth bug" → "fix-auth-bug").

3. If goal is missing, ask the user what the session should accomplish.

4. Call `cortex_session_spawn` with the name, goal, and workspace (default: "default").

5. Report the result: session_id, pane_id, and how to interact:
   - Switch to it: `Ctrl-b n` (next window) or click the tmux tab
   - Send it text: `cortex_session_send <session_id> "text"`
   - Read its output: `cortex_session_capture <session_id>`
   - Close it: `cortex_session_close <session_id>`

## Important

- Always use `cortex_session_spawn` MCP tool — never raw tmux commands for session lifecycle
- The spawned session gets CORTEX_SESSION_ROLE=worker and a system prompt automatically
- Goal is injected into the worker's prompt after CC starts up
