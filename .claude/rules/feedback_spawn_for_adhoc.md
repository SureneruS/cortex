---
name: Spawn workers for ad-hoc tasks proactively
description: When work needs doing in another repo, spawn a worker session, send it the task, monitor, and close — don't rely on existing sessions being available.
type: feedback
---

When the control session needs work done in a specific repo (e.g., updating a skill file in cortex, fixing something in orbit), proactively spawn a short-lived worker session for it. Don't try to send to an existing session that may be closed/unavailable.

**Why:** Existing sessions get closed, paused, or their panes become unavailable. Trying to reuse them leads to errors and wasted time.

**How to apply:** For ad-hoc tasks: spawn → send prompt → monitor completion → close. Keep it self-contained. Don't ask the user to relay the message manually.
