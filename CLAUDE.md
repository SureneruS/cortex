# Nova

Claude Code IDE — session management, memory, and focus tracking.

## Monorepo Structure
- `python/` — Python package (hooks, exchange, rotation, CLI)
- `daemon/` — Rust daemon (PTY manager, IPC server)
- `app/` — Tauri v2 desktop app (Svelte + xterm.js)
- `schemas/` — YAML frontmatter schema definitions (versioned)
- `commands/` — Claude Code slash commands
- `agents/` — Claude Code agent configs (dream, meditate)
- `resources/` — plist templates, fish completions

## Commands
- `cd python && uv run pytest` — run Python tests
- `uv tool install --editable python/` — install CLI tools globally
- `cargo tauri dev` — run Tauri app in dev mode (from app/)
- `cargo build -p nova-daemon` — build the daemon

## Python Conventions
- Python 3.13+, ruff for linting
- TDD: write tests first
- Frontmatter schemas in schemas/ are source of truth
- No python-frontmatter library — custom parser with PyYAML

## Rust Conventions
- Async runtime: tokio
- PTY management: portable-pty
- IPC: Unix socket with JSON-line protocol
- Logging: tracing + tracing-subscriber
