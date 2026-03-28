# Cortex

Companion brain for Claude Code — persistent context, session orchestration, memory.

## Structure
- `cortex/cli/` — Click CLI commands, split by domain (session, stream, cron, pr, misc)
- `cortex/domain/` — models, protocols (TerminalAdapter, repository interfaces), session state machine
- `cortex/services/` — business logic (SessionService). CLI delegates here, not to repos directly.
- `cortex/repositories/` — MongoDB data access (session_repo, message_repo). One per aggregate.
- `cortex/adapters/` — external system wrappers (TmuxAdapter). Implements TerminalAdapter protocol.
- `cortex/container.py` — composition root. Wires repos + adapters + services. `get_container()` singleton.
- `cortex/mongo_state.py` — MongoStateManager (streams, search, dashboards — not yet split into services)
- `cortex/server.py` — MCP server (tools removed, kept for non-channel MCP needs)
- `src/channels-mcp/` — TypeScript channels MCP server (Bun, inter-session messaging)
- `plugin/` — CC plugin (skills, agents, hooks, rules)
- `python/src/nova/` — hooks (legacy Nova, migrating to cortex/)
- `commands/` — slash commands (memorize, handoff, rotate-prep)
- `scripts/` — migration and utility scripts
- `legacy/` — archived code (Tauri app, Rust daemon)
- `.claude/rules/` — project rules loaded by CC in every session

## Architecture
- **CLI-first**: All operations via `cortex` CLI. MCP tools removed (Phase 4). Skills document CLI commands.
- **Layered**: CLI (thin) → Service (business logic) → Repository (data access) + Adapter (external systems)
- **TerminalAdapter protocol**: Abstracts tmux behind a protocol. TmuxAdapter today, Claude Code URI adapter in future.
- **Container**: `get_container()` returns singleton with all repos/adapters/services wired. Reset with `reset_container()` in tests.
- **Session state machine**: `domain/session_states.py` — explicit TRANSITIONS map, `validate_transition()`. Terminal states: completed, dead.
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
- MongoDB for all persistence (repositories, MongoStateManager for streams/search, cron)
- Session commands go through SessionService → repos + TmuxAdapter. Other domains still use MongoStateManager directly (to be migrated).
- `session_registry.py` is a backward-compat shim — real code is in `repositories/session_repo.py`
- httpx for GitHub API (not gh CLI)
- Click for CLI, FastMCP for Python MCP server
- TypeScript/Bun for channels MCP (`src/channels-mcp/`). See `.claude/rules/team-channels.md` for detailed rules.
- `@trace` decorator on all public methods for observability
- All MongoDB IDs as strings (not ObjectIds) in shared collections

## Testing
- Tests use real MongoDB (`cortex_test` / `cortex_state_test` databases), not mocks
- When patching `get_db()`, always call `reset_container()` before and after to clear the singleton
- Mock tmux operations via `patch("cortex.adapters.tmux.TmuxAdapter.<method>")`, not subprocess
- `FakeEmbedder` in conftest.py replaces real sentence-transformers model
