---
name: inline-review
description: Use when the user has added inline comments (# -->) to code files and wants to discuss them before changes are made. Reads comments, responds to each, applies trivial fixes directly, discusses non-trivial ones.
---

# Inline Review

Read inline review comments from modified files, respond to each, and apply or discuss based on complexity.

## Detecting comments

The user adds comments directly in the code using `# -->` as the marker. Search both staged and unstaged changes:

```bash
git diff -U0 HEAD | grep -n '^\+.*# *-->'
```

If `git diff HEAD` doesn't catch them (e.g., new files), also check the working tree:

```bash
grep -rn '# *-->' --include='*.py' $(git diff --name-only HEAD)
```

For each match, extract:
- File path and line number
- The full comment text after `-->`
- 2-3 lines of surrounding code for context

## Responding

1. Apply all trivial changes first (silently)
2. Then present ALL comments as a numbered list — trivial ones marked as done, non-trivial ones with your response
3. This way the user sees one consolidated response with trivial fixes already applied and non-trivial items to discuss

## When to apply directly vs discuss

**Apply directly** (trivial, localized changes):
- Renames (variable, method, field)
- Moving a line/block to a different location in the same file
- Moving logic into a schema converter or similar single-file refactor
- Removing dead code
- Fixing a typo or style issue
- Adding a missing filter condition to a query

**Discuss first** (wait for green signal):
- Refactoring that touches multiple files
- Behavioral changes (different query, different data flow)
- Bug fixes or correctness concerns
- Architectural decisions (where logic lives, new abstractions)
- Anything where you're not 100% sure of the intent

When in doubt, discuss. The cost of asking is low.

## After approval

When implementing discussed changes, remove all `# -->` comments — they are review artifacts, not permanent comments.

## Rules

- Respond to every `# -->` comment found — never skip one
- If a comment asks to "spin an agent" or do research, launch the agent but still present findings before making code changes
- If no comments are found, tell the user

## Examples from real sessions

### Trivial — apply directly

```python
# User comment:
application_id: str | None = None  # --> why not just the list?

# Action: Remove the field, keep application_ids only. Single file, obvious intent.
```

```python
include_feedbacks: bool = False  # --> this is not a filter, should not be in the dataclass

# Action: Move to a method param. Clear instruction, localized change.
```

```python
Feedback.rating.is_not(None),  # --> this should also check for submitted_at

# Action: Add the condition. Direct, single-line fix.
```

### Non-trivial — discuss first

```python
# --> it looks like now we are querying similar data multiple times, can you review this method

# Action: Explain the overlap, propose consolidation approach, wait for approval.
# Why: Touches data flow across multiple methods, could change behavior.
```

```python
# --> let's extract this into a private method here

# Action: Discuss what to extract and where to put it.
# Why: Could be done multiple ways, user may have a preference.
```

```python
interviews_summary=stage_summaries[stage.id],  # --> what's the safest way to handle missing entries?

# Action: Propose options (.get() with default vs None vs ensure all keys exist), discuss tradeoffs.
# Why: Design decision about error handling behavior.
```

```python
summary=InterviewsSummary.from_data(overall_summary) if ... else None,  # --> move this into schema

# Action: Discuss the converter pattern before implementing.
# Why: Architectural decision about where conversion logic lives.
```
