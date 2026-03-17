# Cortex

Companion brain for Claude Code — persistent context, session orchestration, memory.

## Structure
- `cortex/` — MCP server, CLI, GitHub API, cron, daemon
- `python/src/nova/` — hooks, exchange, rotation (legacy Nova, migrating to cortex/)
- `agents/` — dream, meditate agent configs
- `commands/` — slash commands (memorize, handoff, rotate-prep)
- `skills/` — CC plugin skills (babysit-pr, check-watches, dashboard)
- `legacy/` — archived code (Tauri app, Rust daemon)

## Commands
- `uv run pytest` — run all tests
- `uv tool install --editable . --force` — install CLI tools globally
- `cortex session list` — list managed sessions
- `cortex cron list` — list cron jobs
- `cortex daemon status` — check daemon

## Conventions
- Python 3.11+, ruff for linting
- MongoDB for session registry and cron
- httpx for GitHub API (not gh CLI)
- Click for CLI, FastMCP for MCP server
