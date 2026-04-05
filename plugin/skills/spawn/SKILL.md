---
name: spawn
description: Use when the user asks to spawn, create, or start a new worker session — guides through interactive session creation with name, goal, and workspace.
---

# Spawn Session

Create a new Cortex-managed Claude Code worker session in a tmux pane.

## CLI Command

```
cortex session spawn --name <name> [options]
```

## Available Flags

| Flag | Description |
|------|------------|
| `--name` | Session name (required) |
| `--goal` | Purpose description (registry metadata) |
| `--prompt` | First prompt sent to CC after startup |
| `--repo` | Repo under ~/workspace/cercli/ (sets cwd) |
| `--beside <ref>` | Split horizontally beside a session (name, ID prefix, or %pane_id) |
| `--below <ref>` | Split vertically below a session |
| `--color <name>` | CC session color (auto-assigned if omitted, cycles: blue/green/yellow/purple/orange/pink/cyan/red) |
| `--model` | Claude model (haiku, sonnet, opus) |
| `--permission-mode` | CC mode (e.g., plan) |
| `--effort` | CC effort (low, medium, high) |
| `--worktree` | CC worktree name (creates branch + isolated dir) |
| `--resume` | CC session UUID to resume |
| `--split` | Split current pane (legacy, prefer --beside/--below) |
| `--workspace` | default or background |

## Workflow

1. Parse the invocation for pre-filled values:
   - `/spawn` — interactive, ask for details
   - `/spawn fix auth bug in recruitment-backend` — infer name, goal, and repo
   - `/spawn --name worker-1 --repo cortex --goal "fix the auth bug"` — use directly

2. **Infer from goal text**:
   - Repo: if goal mentions a known repo name, suggest `--repo <name>`
   - Name: generate short kebab-case from goal (e.g., "fix auth bug" → "fix-auth-bug")
   - If the user says `/spawn ATS-XXX`, read the Linear ticket to derive goal, repo, and name

3. **Decide placement**:
   - Related to an existing session? Use `--beside` or `--below` that session
   - Two related sessions? Spawn the first as a tab, second `--beside` the first
   - Unrelated? New tab (default behavior)

4. Run `cortex session spawn` with the assembled flags.
   - When `--repo` is provided, always include `--worktree` with name derived from the session name:
     ```
     cortex session spawn --name rb-copy-skill --repo recruitment-backend --worktree rb-copy-skill --goal '...'
     ```

5. Report: session_id, pane_id, color, and how to interact:
   - Switch to it: click the tmux tab or `Ctrl-b n`
   - Send message: `cortex session message <name> "text"`
   - Read output: `cortex session capture <name>`
   - Check layout: `cortex session layout`
   - Close: `cortex session close <name>`

## Examples

```
# Simple
cortex session spawn --name fix-login --repo recruitment-backend --goal "fix login redirect bug"

# Side by side
cortex session spawn --name fe-work --repo frontend
cortex session spawn --name be-work --repo recruitment-backend --beside fe-work

# With prompt
cortex session spawn --name reviewer --repo cortex --prompt "review the latest PR changes"

# Plan mode
cortex session spawn --name planner --repo recruitment-backend --permission-mode plan

# With worktree
cortex session spawn --name feat-avatar --repo recruitment-backend --worktree feat/avatar-upload
```

## Prompt delivery and verification

When spawning with `--prompt`:
1. The prompt is delivered via channels (MongoDB message bus), not tmux.
2. The spawned session is instructed to immediately reply when it receives a new-topic message.
3. **You MUST wait ~15 seconds for a reply** from the spawned session confirming receipt.
4. If no reply arrives, the spawn command automatically resends with a fallback notice.
5. If you still get no reply after that, send the prompt manually via `send_message(to="<session-name>", content="Sending again as last message did not get any response — respond to this message immediately: <original prompt>")`.

## Important

- **ALWAYS use `cortex session spawn`** to create sessions. Never use the Agent tool, subagents, or `claude -p` as a substitute. Cortex spawn handles registry, channels, env vars, and lifecycle — raw alternatives skip all of this.
- Always pass `--worktree` when `--repo` is specified — worktree name defaults to the session name. This ensures workers never edit the main repo directly.
