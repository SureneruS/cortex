---
name: dev-server
description: Use when the user asks to start, stop, check, or switch local dev servers (cercli-backend, recruitment-backend, frontend). Manages a tmux session with all three services.
---

# Dev Server Management

Manage the local development server stack via the `dev-server` fish function and tmux.

## Commands

The `dev-server` fish function (at `~/.config/fish/functions/dev-server.fish`) manages a tmux session called `dev-server` with three windows.

### Available subcommands

| Command | What it does |
|---------|-------------|
| `dev-server start` | Pull latest main, install deps, start all 3 servers |
| `dev-server stop` | Gracefully stop all servers, kill tmux session |
| `dev-server status` | Show which directory each server runs from |
| `dev-server switch <service> <target>` | Switch a service to a branch/worktree/path |
| `dev-server logs <service>` | Attach to a service's tmux window |

### Services and ports

| Service | Port | Stack |
|---------|------|-------|
| cercli-backend | https://portal.localhost:8000 | Django, Poetry, HTTPS via runserver_plus |
| recruitment-backend | http://localhost:8080 | FastAPI, uv, Docker Compose |
| frontend | http://localhost:3000 | Next.js, pnpm, turbo |

## Prerequisite

This skill requires the `dev-server` fish function. Before invoking, check it exists:

```bash
fish -c 'type -q dev-server' && echo "ok" || echo "missing"
```

If missing, tell the user to run: `ln -sf ~/workspace/cercli/cortex/plugin/host/fish/dev-server.fish ~/.config/fish/functions/dev-server.fish`

See `plugin/host/SETUP.md` for details.

## Workflow

### Starting servers

When the user asks to start dev servers or needs them running:

1. Check if already running: `dev-server status`
2. If not running: `dev-server start`
3. Servers take 30-60 seconds to fully boot. Use health checks to verify:
   - cercli-backend: `curl -sk https://portal.localhost:8000/health` (may need a few retries)
   - recruitment-backend: `curl -s http://localhost:8080/health`
   - frontend: `curl -s http://localhost:3000`

### Checking status

Run `dev-server status` via Bash. If the tmux session doesn't exist, servers aren't running.

For deeper checks, verify the HTTP endpoints respond:
```bash
curl -sk -o /dev/null -w "%{http_code}" https://portal.localhost:8000/health
curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/health
curl -s -o /dev/null -w "%{http_code}" http://localhost:3000
```

### Switching a service to a worktree branch

When the user wants to test a feature branch on a running server:

1. `dev-server switch recruitment-backend feat/ATS-123-feature` — looks in `.worktrees/`
2. `dev-server switch recruitment-backend main` — switches back to main repo
3. `dev-server switch recruitment-backend /full/path/to/worktree` — arbitrary path

The switch stops the current server, cd's to the target, installs deps, and restarts.

### Stopping servers

`dev-server stop` — sends Ctrl+C, runs docker compose down for recruitment-backend, kills the tmux session.

## Important

- Run all commands via Bash tool using `fish -c 'dev-server <subcommand>'` since the default shell is fish but Bash tool uses bash.
- The `start` command runs `git checkout main && git pull` — only use on clean repos. If there are uncommitted changes, warn the user.
- `switch` does NOT run git operations — the target directory should already be at the right state.
- Frontend no longer needs sudo (root-owned node_modules were fixed).
- If a server fails to start, use `dev-server logs <service>` equivalent: `tmux capture-pane -t dev-server:<service> -p | tail -30` to see the error.
