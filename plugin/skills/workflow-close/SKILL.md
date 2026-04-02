---
name: workflow-close
description: Use when implementation is done and you're ready to ship — after execution. Handles repo health, commit, PR, learning capture, and cleanup.
---

# Close

Ship the work, capture learnings, clean up. This phase is skip-resilient — it works regardless of which prior phases were completed.

## Step 1: Repo Health (before PR)

Update the repo with knowledge gained during this work. These are for future sessions in this repo — not cortex memory.

### CLAUDE.md Updates

Add patterns, conventions, or gotchas discovered that apply broadly to the repo:
- New architectural patterns used
- Integration points discovered
- Conventions established

Only add what's genuinely useful for future sessions. Don't add noise.

### .claude/rules/ Files

Add specific behavioral rules when a gotcha is likely to recur:
- File format: `feedback_<descriptive_name>.md`
- Structure: rule statement, **Why:** context, **How to apply:** guidance
- Only for non-obvious things that would save future sessions from repeating mistakes

### What NOT to Add

- Don't document what's obvious from the code
- Don't add rules for one-off situations
- Don't duplicate existing rules — check first

## Step 2: Ship

### Commit

- Conventional format linked to Linear ticket: `type(ATS-XXX): description`
- Types: feat | fix | chore | docs | style | refactor | perf | test | build | ci | revert
- Stage specific files — don't `git add -A`

### PR

- Title matches commit format
- Body: summary bullets, test plan
- Link to Linear ticket
- Never reference cortex in PR content

## Step 3: Capture to Cortex Memory

Structured capture — separate from repo health:
- **What was learned:** Decisions made, patterns discovered, gotchas hit
- **What didn't work:** Approaches tried and failed, with reasons (anti-retry for future sessions)
- **Tags:** Component, module, repo — for active retrieval in future align/plan phases

Use the cortex memory system (auto-memory write). Include enough context that a future session querying by component/module would find this useful.

## Step 4: Clean Up

- Remove worktree: `git worktree remove <path>` (or ExitWorktree with action: remove)
- Update workflow state to complete
- Update cortex stream

## Step 5: Offer Next Steps

- Babysit PR — invoke existing `babysit-pr` skill if user wants autonomous monitoring
- Check CI status — `gh pr checks`
- Review comments — offer to check and respond

## Skip Resilience

If jumping to close from any earlier phase:
- Commits what's there
- Creates PR from current branch state
- Still does repo health + capture (skip if nothing was learned)
- Still cleans up worktree and state

## What NOT to Do

- Do not create a PR without updating CLAUDE.md/rules first (repo health comes before shipping)
- Do not skip the "what didn't work" capture — failed approaches are as valuable as successes
- Do not reference cortex in any external-facing content (Linear, PR, Slack)
- Do not auto-merge — always let the user or babysit-pr handle merge decisions
