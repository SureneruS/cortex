---
description: Capture session learnings to Nova memory
allowed-tools: Bash(ls:*), Bash(stat:*), Read, Write(~/.nova/memory/captures/**)
---

Capture what this session has learned and write it to Nova memory.

## Step 1: Determine Session Metadata

Find the current session's transcript to get the session ID:

```bash
ls -t ~/.claude/projects/*/?.jsonl 2>/dev/null | head -1
```

The session ID is the filename stem (without .jsonl extension). If you can't find it, generate a short random ID.

Determine repos from the current working directory and any other repos you've worked with in this conversation.

## Step 2: Reflect on This Conversation

Think about what happened in this session. Extract:

1. **What was worked on** — the task, feature, or bug
2. **Key decisions made** — and why (the reasoning matters more than the choice)
3. **Patterns learned** — reusable insights, gotchas discovered, things that would help future sessions
4. **What's pending** — unfinished work, next steps, blockers

Focus on things a FUTURE session would benefit from knowing. Skip:
- Routine operations (ran tests, committed code)
- Obvious things the codebase already documents
- Transient state (exact line numbers that will change)

## Step 3: Write the Capture File

Write a markdown file with YAML frontmatter to `~/.nova/memory/captures/`.

**Filename format:** `YYYY-MM-DD-HHMMSS-{session_id_first_8_chars}.md`

**File structure:**
```
---
session: {session_id}
repos: [{repo_names}]
transcript: {path_to_transcript_jsonl}
captured_at: {ISO 8601 timestamp}
schema_version: 1
---

{Your reflection from Step 2 — written as clear, concise prose.
Each insight should be self-contained.
Use paragraphs to separate distinct topics.}
```

## Step 4: Confirm

Report what was captured: the filename and a 1-2 line summary of the key insights.
