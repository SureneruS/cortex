---
name: feedback_never_force_close_sessions
description: Never force-close sessions without explicit user approval — closing is destructive and loses learnings
type: feedback
---

Never close sessions (especially --force) without explicit user approval. Closing a session is destructive — it skips memorize, loses learnings, kills the pane.

**Why:** Suren explicitly stopped a force-close of stale sessions. Even "obviously dead" sessions may have uncommitted work or learnings worth extracting.

**How to apply:** Always ask before closing any session. Present the list of sessions to close and wait for approval. Never batch-close. The control session should manage lifecycle carefully, not aggressively.
