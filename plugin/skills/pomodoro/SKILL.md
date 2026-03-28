---
name: pomodoro
description: "Use when the user says /pomodoro, /pomo, or asks to start/stop/check a focus timer"
user_invocable: true
---

# Pomodoro Timer

Manage a focus timer via the statusline. The timer state lives at `~/.claude/cache/pomodoro`.

## Commands

Parse the user's intent from their message:

- **start** (default if no arg): `touch ~/.claude/cache/pomodoro` — starts a 25-minute timer
- **stop** / **cancel**: `rm -f ~/.claude/cache/pomodoro` — stops the timer
- **status** / **check**: Check if file exists and show remaining time

## Implementation

1. Run the appropriate shell command via Bash tool
2. Confirm the action with a short message:
   - Start: "🍅 Pomodoro started — 25 minutes. Focus!"
   - Stop: "🍅 Pomodoro cancelled."
   - Status: Show time remaining or "No active pomodoro"

## Duration Override

If the user says `/pomodoro 15` or "start a 10 min pomodoro", note that the statusline hardcodes 25 min (`POMODORO_MINS`). Tell them to edit `~/.claude/statusline-enhanced.fish` line 17 area if they want a different default. The timer file's mtime is the start time — the statusline calculates remaining from that.
