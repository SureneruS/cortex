---
name: memorize
description: Capture session insights to ~/cortex/captures/ for the dream pipeline. Use at end of session or when a significant insight, pattern, or gotcha is discovered.
---

# Memorize

Capture reusable insights from the current session. You have full conversation context — extract what would help future sessions.

## What to capture

- **Patterns** — approaches that worked (or didn't)
- **Gotchas** — non-obvious traps that caused trouble
- **Decisions** — architectural choices and their reasoning
- **Conventions** — coding patterns specific to a repo

## What NOT to capture

- Session-specific state (current task details, in-progress work)
- Routine operations (ran tests, committed, pushed)
- Anything already in CLAUDE.md or .claude/rules/

## Workflow

1. Reflect on the session — what insights, patterns, gotchas, or decisions emerged?
2. Write ONE capture file to `~/cortex/captures/` with the format below
3. Group related insights into a single file. One file per session is typical.

## Capture format

```markdown
---
source: memorize
session_name: {CORTEX_SESSION_NAME or "manual"}
captured_at: "{ISO timestamp}"
repos: [{repo names involved}]
---

## {Topic 1}

{Actionable insight. Lead with the rule, then the reasoning.}

## {Topic 2}

{Another insight...}
```

## File naming

`YYYY-MM-DD-{session_name}-memorize.md`

Example: `2026-04-06-ctx5-nova-audit-memorize.md`

## Pipeline

This file feeds the **dream** agent, which consolidates captures into structured knowledge files in `~/cortex/knowledge/`. Dream runs via `cortex dream` (manually or on cron). You don't need to worry about deduplication — dream handles that.
