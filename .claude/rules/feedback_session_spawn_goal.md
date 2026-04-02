---
name: session_spawn goal vs prompt params
description: goal is registry metadata only, prompt is what gets typed into the session — use prompt OR session_send, not both
type: feedback
---

After CTX-34 fix: `goal` is registry metadata only (shows in session_list/session_get). The new `prompt` param controls what gets typed into the session.

**Why:** Old behavior typed the goal as a prompt AND stored it, causing double-prompting when using session_send.

**How to apply:**
- `goal`: always set for discoverability in session_list
- `prompt`: use for simple one-shot tasks that don't need follow-up
- `cortex_session_send`: use for complex multi-part instructions after spawn
- Never use both `prompt` and `cortex_session_send` — pick one delivery method
