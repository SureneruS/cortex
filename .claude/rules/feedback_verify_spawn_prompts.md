---
name: Verify large spawn prompts with user first
description: Before spawning sessions with large/complex prompts, check with user to avoid wasted work
type: feedback
---

Before spawning worker sessions with large prompts, verify the prompt with the user first.

**Why:** Prompt bloat audit was spawned with a long detailed prompt that asked for the wrong thing (system prompt breakdown instead of hook injection impact). The wasted session cost tokens and time.

**How to apply:** When crafting a spawn prompt that's more than 2-3 sentences, draft it and show the user before spawning. Quick one-liner tasks are fine to fire immediately.
