Every Cortex feature change must be cohesively wired to all consumers. A feature that emits data without updating all relevant surfaces is incomplete.

**The integration surfaces:**
1. **Session registry** — runtime state, last_activity, metadata. Source of truth for list/health/dashboard.
2. **Channel events** — structured messages to parent/control sessions. Real-time notification.
3. **Dashboard/TUI** — must reflect any new state or data.
4. **CLI commands** — list, get, health must surface new fields.
5. **Streams** — log meaningful state changes.

**The rule:** When implementing a feature that produces or changes state:
- Update the session registry (so list/health/dashboard see it)
- Emit a channel event (so control/parent sessions see it)
- Verify the dashboard/TUI renders it
- Ensure CLI commands surface it

A hook that emits a channel message but doesn't update the registry is half-wired. A registry update without a channel event leaves control blind. Both must happen.

**Why:** Features shipped in isolation create an ecosystem where each piece works alone but nothing works together. The dashboard shows stale data, session list misses runtime state, control sessions can't see worker activity. This compounds over time.

**How to apply:** Before marking any Cortex feature as done, check: "Can I see this state from session list? From the dashboard? Does control get notified?" If any answer is no, the feature is incomplete.