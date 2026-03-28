---
name: weekstart
description: Use when starting a new week — loads the latest checkpoint, pulls fresh state on carry-over items, and facilitates interactive planning.
---

# Weekly Start

Load the previous week's checkpoint, refresh state, and plan the new week.

## Workflow

### 1. Load checkpoint

Call `cortex_get_checkpoint()` (no args = latest). If no checkpoint exists, note it and proceed with manual context gathering — ask the user what carried over.

### 2. Pull fresh state

For each carry-over item in the checkpoint, check current status:
- **PRs**: `gh pr view <number> --repo <repo> --json state,mergedAt` — have any merged since the checkpoint?
- **Linear tickets**: Check ticket states via Linear MCP if available.
- **New PRs**: `gh pr list --repo <repo> --state open --author SureneruS` — anything new since the checkpoint?

### 3. Present the picture

Show:
- **Last week summary** — brief recap from the checkpoint
- **What changed since checkpoint** — PRs merged, tickets moved, new items
- **Carry-over items** — what's still pending, with updated status
- **Active Cortex streams** — from `cortex_get_active_streams`
- **Knowledge effectiveness**: If `~/.nova/memory/effectiveness.jsonl` exists and has 10+ sessions of data since last review, flag it: "Nova knowledge has N sessions of effectiveness data — review to prune irrelevant entries." Show top 3 most-used and top 3 most-irrelevant entries by frequency.

### 4. Interactive planning

Ask the user to set priorities for the week. Listen for:
- What's top of mind
- External dependencies or blockers
- FE/team needs that affect BE priorities
- Any new work items or tickets

Help organize into a prioritized list. Don't over-structure — follow the user's lead on how detailed they want to be.

### 5. Update Cortex

After planning is agreed:
- Update relevant Cortex streams with new week's goal tags via `cortex_update_stream` (metadata: `{"goal": "weekly-YYYY-MM-DD"}`)
- Log any planning decisions via `cortex_log_decision` if significant
