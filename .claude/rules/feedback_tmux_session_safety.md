---
name: tmux session safety rules
description: Never kill tmux sessions/server — deny rules in settings.json, use remain-on-exit, confirm before destructive ops
type: feedback
---

tmux kill-server and tmux kill-session are in the deny list in settings.json. Never run them.

**Why:** A single tmux kill-server destroys ALL running sessions including long-running CC workers. The user's primary concern is accidentally approving a command that nukes everything.

**How to apply:**
- The deny rules block `tmux kill-server*` and `tmux kill-session *` from CC
- To close individual panes: `tmux kill-pane -t %id` (allowed, scoped to one pane)
- When closing a Cortex session: use `cortex_session_close` which handles both registry and pane cleanup
- `remain-on-exit on` in tmux.conf means dead panes show [Exited] instead of vanishing
- Confirm prompts on `Prefix + x` (kill-pane) and `Prefix + X` (kill-window)
