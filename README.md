# Cortex

Companion brain for Claude Code: persistent memory across sessions, session orchestration, and an inter-session message bus delivered over MCP.

Cortex tracks long-running *work streams* (decisions, updates, checkpoints) so a fresh Claude Code session can pick up where the last one stopped, spawns and supervises child sessions in tmux, runs cron-scheduled actions through a daemon, and watches GitHub PRs for review threads and CI. Every session it spawns gets a channels MCP server, so sessions can message each other and the daemon can route messages to a human.

## Status

Personal tooling, built and used daily February–April 2026. It assumes a local MongoDB, tmux, `gh`, and Claude Code with the channels research preview enabled. It is published as a reference implementation, not a packaged product — expect hard-coded workspace conventions in a few places.

## The MCP arc

This repo went through two MCP designs, and the history keeps both:

1. **Tool-heavy server (Feb–Mar 2026).** `cortex/server.py` started as a FastMCP server with 43 tools across six clusters — stream memory, checkpoints, dashboard, cron, daemon, session orchestration, PR ops. Every operation was an MCP tool. See the tree at any commit before `bf699ed`.
2. **CLI-first + channels MCP (from 2026-03-20).** The tools were removed (`bf699ed`, "Phase 4") in favour of a Click CLI that prints Rich on a TTY and JSON when piped. Skills document CLI commands instead of tool schemas. MCP was kept for the one thing a CLI cannot do: **push** into a live session. `src/channels-mcp/` is a small TypeScript (Bun) server exposing `send_message`, `get_messages`, `get_status`, `poll_query`, `ttl_cleanup`; it polls a MongoDB `messages` collection and emits `notifications/claude/channel` into the session it is attached to.

The lessons that forced the second design are written down in [`.claude/rules/team-channels.md`](.claude/rules/team-channels.md): deliver only after `oninitialized` or messages are lost, write-first ordering, atomic `findOneAndUpdate` claims plus an in-process set for two-layer dedup, `setTimeout` recursion instead of `setInterval`, a 10-message poll cap against context flooding, and the system prompt via the MCP `instructions` field rather than CLAUDE.md.

## Layout

```
cortex/cli/           Click commands by domain (session, stream, cron, pr, misc)
cortex/domain/        models, protocols (TerminalAdapter, repositories), session state machine
cortex/services/      business logic; CLI delegates here
cortex/repositories/  MongoDB access, one per aggregate
cortex/adapters/      external systems (tmux)
cortex/container.py   composition root
cortex/server.py      FastMCP server (tools removed in Phase 4; kept for non-channel MCP needs)
cortex/daemon.py      cron executor, health checks, human message routing
src/channels-mcp/     TypeScript channels MCP server (inter-session messaging)
plugin/               Claude Code plugin: skills, agents, hooks, rules
commands/             slash commands (memorize, handoff, rotate-prep)
python/src/nova/      legacy hooks (predecessor project)
legacy/               archived Tauri app and Rust daemon
tests/                pytest suite (real MongoDB, tmux mocked at the adapter)
```

Architecture rules the code follows: CLI → Service → Repository + Adapter; all MongoDB IDs are strings (pymongo and the Node driver must agree); `@trace` on public service methods; timestamps shown in local time.

## Running

```bash
uv sync
uv run python -m pytest tests/            # unit + integration (needs local MongoDB)
uv run python -m pytest tests/ -m e2e     # spawns real tmux panes
uv tool install --editable . --force      # installs the `cortex` CLI
cd src/channels-mcp && bun install && bun test
```

`config.example.json` shows the repo map the session spawner expects; copy it to `~/.cortex/config.json` and point the paths at your own checkouts.
