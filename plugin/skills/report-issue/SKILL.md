---
description: Use proactively whenever you encounter ANY tooling issue, unexpected behavior, missing capability, or improvement idea — even minor ones. Trigger on silent failures, wrong outputs, stale data, workarounds, missing API support, confusing DX, or any "this should be better" moment. Do NOT wait to be asked. Do NOT skip small issues.
---

# Report Issue

Create a Linear ticket in the Cortex team. Use for both bugs and feature requests.

**IMPORTANT:** Only use `mcp__linear-personal__save_issue` to create tickets. If Linear MCP fails for any reason, fall back to writing a file at `~/cortex/issues/YYYY-MM-DD-<slug>.md` with the same content. Do NOT use any other Linear MCP (e.g. `claude_ai_Linear_2`), GitHub issues, or other tracking systems.

## When to use

**Bugs (proactively, without being asked):**
- A tool returns empty, wrong, or unexpected output
- A registry has stale data
- A workaround was required to complete a task
- Behavior contradicts documented behavior
- An error was silently swallowed
- A tool is slow, flaky, or requires retries

**Feature requests (when identified during work):**
- A capability is missing that would have been useful
- An existing tool needs a new parameter or mode
- A workflow could be streamlined
- DX friction — anything that made you think "this should be easier"

## Steps

1. Determine type: **bug** or **feature**

2. Create the Linear ticket using `mcp__linear-personal__save_issue`:
   - `team`: "Cortex"
   - `state`: "Triage"
   - `labels`: ["bug"] or ["feature"]
   - `title`: concise description
   - `description`: use the template below
   - No assignee, no priority

3. Output one line: `Issue logged: <ticket-id> — <title> (<linear-url>)`

## Description templates

### Bug
```
**Skill:** <skill that was running, if applicable>
**Component:** <tool/service/file affected>

## What happened
<concrete description — include exact output if useful>

## Expected
<what should have happened>

## Workaround
<what you did instead, if applicable>

## Suggested fix
<only if obvious>
```

### Feature request
```
**Component:** <tool/service affected>

## Use case
<what you were doing when you needed this>

## Proposal
<what the feature would do>
```

Keep it factual and brief.
