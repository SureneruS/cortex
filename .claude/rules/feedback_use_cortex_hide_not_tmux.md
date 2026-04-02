---
name: Use cortex session hide, not raw tmux move-pane
description: Moving panes to background must go through cortex session hide, not raw tmux commands — tmux move-pane merges into existing windows instead of creating new tabs.
type: feedback
---

Use `cortex session hide <id>` to move sessions to background, not `tmux move-pane`.

**Why:** `tmux move-pane` merges the pane as a split into an existing window, making it tiny and hard to find. `cortex session hide` does `break-pane` + `move-window` which creates a proper full-size tab. This also updates the registry status to `hidden`.

**How to apply:** For any session lifecycle operation (hide, show, close, spawn), always use the cortex CLI command. Raw tmux is only for reading (capture-pane, list-panes) or when cortex doesn't have a command for it.
