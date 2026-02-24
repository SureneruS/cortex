---
description: Capture session learnings to Nova memory
allowed-tools: Bash(ls:*), Bash(stat:*), Read, Write(~/.nova/memory/captures/**)
---

Capture what this session has learned and write it to Nova memory. These captures are processed by the Dream agent into knowledge files, so structure matters.

## Step 1: Determine Session Metadata

Find the current session's transcript to get the session ID:

```bash
ls -t ~/.claude/projects/*/?.jsonl 2>/dev/null | head -1
```

The session ID is the filename stem (without .jsonl extension). If you can't find it, generate a short random ID.

Determine repos from the current working directory and any other repos you've worked with in this conversation.

## Step 2: Extract Insights

Review this conversation and extract distinct, reusable insights. For each one, write a separate section with a descriptive heading.

Focus on:
- **Patterns** — approaches that worked (or failed) and could apply to future work
- **Gotchas** — non-obvious traps, surprising behavior, things that wasted time
- **Decisions** — architectural or design choices AND the reasoning behind them
- **Conventions** — repo-specific patterns that aren't documented elsewhere

For each insight, include:
- **What** — the pattern, gotcha, or decision (concise)
- **Why** — the reasoning or what triggered this learning
- **Context** — enough detail that a future session can act on this without the full conversation

Skip:
- Routine operations (ran tests, committed, pushed)
- Task progress updates ("finished step 3 of 5")
- Information that's already in CLAUDE.md or repo docs

## Step 3: Write the Capture File

Write to `~/.nova/memory/captures/` with filename: `YYYY-MM-DD-HHMMSS-{session_id_first_8_chars}.md`

```markdown
---
session: {session_id}
repos: [{repo_names}]
transcript: {path_to_transcript_jsonl}
captured_at: {ISO 8601 timestamp}
schema_version: 1
---

### {Descriptive heading for insight 1}

{What, why, and context for this insight.}

### {Descriptive heading for insight 2}

{What, why, and context for this insight.}
```

Each `###` section should be a self-contained insight that dream can extract into its own knowledge file. Use descriptive headings — not "Lesson 1" but "SQLAlchemy transaction ordering for external API calls".

### Example: Good vs Mediocre

Mediocre:
> Built Nova Phase 1. Used Python 3.13 with src layout. The hook format was wrong and we fixed it. Dream agent processes four sources in priority order.

Good:
> ### Claude Code hook output format requires hookSpecificOutput wrapper
>
> Hooks must return `{"hookSpecificOutput": {"hookEventName": "...", "additionalContext": "..."}}` — not just `{"additionalContext": "..."}`. The simpler format silently fails with no error. Discovered when SessionStart injection appeared to work (no errors) but context never appeared in sessions.

The good version is a self-contained gotcha with enough context to act on. The mediocre version is a summary that dream can't extract patterns from.

## Step 4: Confirm

Report the filename and list each insight heading with a one-line summary.
