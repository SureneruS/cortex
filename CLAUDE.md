# Cortex

Companion brain for Claude Code — persistent context, session orchestration, memory.

## Structure
- `cortex/` — CLI (Click), MongoDB state (MongoStateManager), GitHub API, cron, daemon, observability
- `cortex/server.py` — MCP server (tools removed, kept for channels)
- `plugin/` — CC plugin (skills, agents, hooks, rules)
- `python/src/nova/` — hooks (legacy Nova, migrating to cortex/)
- `commands/` — slash commands (memorize, handoff, rotate-prep)
- `scripts/` — migration and utility scripts
- `legacy/` — archived code (Tauri app, Rust daemon)

## Architecture
- **CLI-first**: All operations via `cortex` CLI. MCP tools removed (Phase 4). Skills document CLI commands.
- **MongoDB**: All data — streams, updates, decisions, checkpoints, sessions, dashboards. SQLite only for vector embeddings (vec.db).
- **structlog**: Two levels — info (business events) + debug (auto-trace via `@trace`). Zero silent failures.
- **Plugin**: Marketplace at `.claude-plugin/`, plugin at `plugin/`. Skills, agents, hooks, rules.

## Commands
- `uv run python -m pytest tests/` — run all tests
- `uv tool install --editable . --force` — install CLI tools globally
- `cortex stream list` — list active streams
- `cortex stream log <id> --content "..." --summary "..."` — log update
- `cortex session list` — list managed sessions
- `cortex cron list` — list cron jobs
- `cortex daemon status` — check daemon

## Conventions
- Python 3.11+, ruff for linting
- MongoDB for all persistence (MongoStateManager, session_registry, cron)
- httpx for GitHub API (not gh CLI)
- Click for CLI, FastMCP for MCP server (channels only)
- `@trace` decorator on all public methods for observability
