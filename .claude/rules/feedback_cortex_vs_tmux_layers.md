---
name: Cortex is the registry, tmux is the execution layer
description: cortex_session_spawn handles BOTH registry (MongoDB) and terminal (tmux). Don't confuse the layers — tmux doesn't track sessions, Cortex does.
type: feedback
---

When asked to "create a session," use `cortex_session_spawn` — NOT raw tmux commands.

**Why:** Cortex session spawn does two things: (1) registers the session in MongoDB with metadata (name, role, workspace, spawned_by, status) and (2) creates the tmux pane. Raw tmux only does the terminal part — no registry, no metadata, no tracking.

**How to apply:**
- `cortex_session_spawn` = create session (registry + tmux pane)
- `cortex_session_close` = close session (registry + kill pane)
- `cortex_session_list` / `cortex_session_get` = query registry
- Raw `tmux capture-pane` / `tmux send-keys` = interact with existing panes (fine for monitoring, not for lifecycle)
- tmux is the execution layer INSIDE cortex_session_spawn, not a competing system
