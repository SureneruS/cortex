---
name: wrapup
description: Use when wrapping up the week — gathers data from all available sources, generates a weekly summary, presents for review, and saves as a Cortex checkpoint.
---

# Weekly Wrapup

Generate a comprehensive weekly checkpoint by gathering data from all available sources.

## Workflow

### 1. Determine the week

Get today's date and calculate the Monday of the current week (ISO format, e.g., "2026-03-03"). This is the `week_of` key.

### 2. Gather data adaptively

Try each source. If a source is unavailable (MCP disconnected, auth expired), note it and continue.

**Always available:**
- **GitHub** (`gh` CLI): Your merged PRs, team merged PRs, open PRs — across `cercli/recruitment-backend`, `cercli/cercli-backend`, `cercli/frontend`. Use `gh pr list --state merged --search "merged:>=YYYY-MM-DD author:SureneruS"` and similar.
- **Cortex** (`mcp__cortex__*`): Active streams, recent updates and decisions.

**May need auth:**
- **Linear** (`mcp__claude_ai_Linear_2__*`): Ticket states for active work, cycle progress.
- **Granola** (`mcp__granola__*`): Meeting summaries, action items, key decisions from the week.
- **Slack** (`mcp__plugin_slack_slack__*`): Key messages sent by Suren (`from:<@UXXXXXXXXXX>`), important conversations.
- **Notion** (`mcp__claude_ai_Notion__*`): Docs created or updated this week.
- **Calendar** (`mcp__claude_ai_Google_Calendar__*`): Meetings attended.

For each unavailable source, include a note in the output: "Source X unavailable — not checked."

### 3. Generate checkpoint content

Freeform markdown. Adapt the structure to the week — not every section is needed every time. Use these as guidelines:

- **What shipped** — merged PRs with links, grouped by repo
- **In progress** — open PRs, active work items
- **Spillover to next week** — what didn't land and why
- **Unplanned work** — things that came up mid-week
- **Team output** — other team members' merged PRs (brief)
- **Meetings and decisions** — key outcomes from meetings
- **FYI / context** — things worth noting but not actionable

Always include PR links in format `[#123](https://github.com/cercli/repo/pull/123)`.

### 4. Present for review

Show the generated checkpoint to the user. Wait for corrections. Common corrections:
- Items miscategorized (e.g., "this is in progress, not done")
- Missing context ("careers bug is not related to shadow roles")
- Scope corrections ("get feedback is split into two APIs")

Apply corrections and re-present if significant changes were made.

### 5. Save checkpoint

Call `cortex_save_checkpoint` with:
- `week_of`: the Monday date
- `content`: the reviewed markdown
- `stream_ids`: auto-captured (omit parameter)

### 6. Update Cortex streams

Log weekly markers on relevant active streams using `cortex_log_update`. Only streams that had meaningful activity this week.
