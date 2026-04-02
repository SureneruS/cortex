---
name: Never silently ignore Cortex errors
description: When a Cortex MCP call fails (e.g. writing to a completed stream), investigate and fix — don't skip silently
type: feedback
---

When a Cortex MCP tool call fails, STOP and handle the error — don't silently move on.

**Why:** Suren caught me ignoring a failed `cortex_log_update` to a completed stream. I skipped it and moved on without checking for the right stream. Silent failures mean lost context.

**How to apply:** If a Cortex call returns an error: (1) read the error message, (2) check `cortex_get_active_streams` to find the right target, (3) retry with the correct stream/entry. Never assume "it's fine" — Cortex is the second brain, lost updates are lost context.
