---
name: Force-close empty sessions without asking
description: Sessions that haven't received meaningful input can be force-closed immediately — no need to ask for approval
type: feedback
---

Force-close sessions that haven't received any meaningful input (no prompt sent, no work done) — don't ask for approval first.

**Why:** The "never close without approval" rule is about protecting sessions with work/learnings. Empty sessions have nothing to lose — asking adds unnecessary friction.

**How to apply:** When closing a session to respawn it elsewhere (wrong repo, wrong config), check if it received any prompts or did any work. If empty, `cortex session close <name> --force` immediately. Only ask for approval when the session has done actual work.
