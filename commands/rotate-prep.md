---
description: Memorize session learnings and prepare handoff for rotation
allowed-tools: Bash(ls:*), Bash(stat:*), Read, Write(~/.nova/memory/captures/**)
---

You are about to be rotated. Complete BOTH steps below before finishing.

## Step 1: Memorize

Capture what this session has learned. Write to `~/.nova/memory/captures/` with filename: `YYYY-MM-DD-HHMMSS-{session_id_first_8_chars}.md`

Find the session ID:

```bash
ls -t ~/.claude/projects/*/?.jsonl 2>/dev/null | head -1
```

Extract distinct, reusable insights (patterns, gotchas, decisions, conventions). Skip routine operations and task progress.

```markdown
---
session: {session_id}
repos: [{repo_names}]
transcript: {path_to_transcript_jsonl}
captured_at: {ISO 8601 timestamp}
schema_version: 1
---

### {Descriptive heading}

{What, why, and context.}
```

If this session had no meaningful insights, skip the capture file — don't write an empty one.

## Step 2: Handoff

After memorizing, output a structured handoff summary for your replacement session:

**## Goal** — What you're working on (one sentence)

**## Progress** — What's done (bullet points)

**## Pending** — What's left (bullet points with priority)

**## Blockers** — Open questions or decisions needed

**## Key Context** — Important files, decisions, branches, PRs

**## Where You Left Off** — Exactly what you were doing when stopped

Be comprehensive but concise. The handoff summary becomes the starting prompt for the next session.
