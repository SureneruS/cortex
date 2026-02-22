# Nova

Memory system for Claude Code sessions — capture, inject, dream.

## Commands
- `uv run pytest` — run tests
- `uv tool install --editable .` — install CLI tools globally
- `nova-setup` — create ~/.nova/ directory structure

## Structure
- `src/nova/` — Python package (src layout)
- `schemas/` — YAML frontmatter schema definitions (versioned)
- `commands/` — Claude Code slash commands
- `agents/` — Claude Code agent configs
- `tests/` — pytest tests

## Conventions
- Python 3.13+, ruff for linting
- TDD: write tests first
- Frontmatter schemas in schemas/ are source of truth
- No python-frontmatter library — custom parser with PyYAML
