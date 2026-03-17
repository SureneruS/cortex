## Preferences
- [2026-03-16] migrated: Rich Live -> Textual (scrollable content, keyboard shortcuts, clean resize)
- [2026-03-16] preference (superseded): rich framework was initial choice; migrated to textual for scrolling
- [2026-03-16] preference: use symbols alongside colors (shape conveys meaning independently)
- [2026-03-16] preference: compact density, monospace, no emojis
- [2026-03-16] preference: important things prominent (bold, bright), less important dimmed/muted
- [2026-03-16] preference: dashboard CAN be longer — no 80x24 constraint, use full terminal height
- [2026-03-16] preference: sections — weekly goals (grouped: feedback prominent, other, completed, unplanned, distractions), open PRs, WIP, backlog, resources+links
- [2026-03-16] preference: pending goals should be BRIGHT, done goals DIMMED — opposite of typical styling. Important = visible.
- [2026-03-16] preference: feedback management goals are the week's focus — give them a separate highlighted sub-section

## Feedback
- [2026-03-16] improvement/normal: user liked the initial output — no visual complaints on first render
- [2026-03-16] bug/normal (resolved): scroll wheel garbage chars — was Rich Live issue, Textual handles mouse/scroll natively
- [2026-03-16] improvement/critical: pending items were dim (bright_black) making important things invisible — flipped: pending=bold bright, done=bright_black

## Backlog
- ~~keyboard shortcuts (q: quit, r: refresh) — needs raw stdin or curses~~ DONE via Textual migration
- auto-detect "unplanned" vs "distraction" classification
- --once mode explanation: prints snapshot and exits (useful for Claude Code preview); live mode is the primary usage

## Decisions
- [2026-03-16] decision: goals sorted pending-first, done-last — keeps focus on what needs work
- [2026-03-16] decision: goals grouped: feedback management (cyan bold) > other pending (bold) > completed (dimmed) > unplanned > distractions
- [2026-03-16] decision: feedback goals detected by linear ticket ID in FEEDBACK_TICKETS set — update set when epic changes
- [2026-03-16] decision: PR titles strip conventional commit prefix for readability
- [2026-03-16] decision: draft PRs only shown if referenced in goals or recent (<14 days), collapsed with "+N more"
- [2026-03-16] decision: review threads shown as "N open" (red) or "all ok" (green) — actionable signal
- [2026-03-16] decision: resources compact on single line, blockers highlighted red below
- [2026-03-16] decision: data lives in week.json, updated by Claude during sessions; PRs fetched live from gh CLI
- [2026-03-16] decision: week.json supports "wip" and "backlog" arrays for non-goal items
- [2026-03-17] decision: live mode uses Textual App with bordered Container panels, VerticalScroll, 2min PR refresh, 1s data re-read
- [2026-03-17] decision: keyboard shortcuts: q=quit, r=force refresh PRs (via Textual bindings + Footer widget)
- [2026-03-17] decision: PR fetching runs in Textual worker thread (non-blocking), exclusive=True prevents pile-up
- [2026-03-17] decision: links use Textual @click markup (not Rich link style) — Rich OSC 8 stripped by Textual pipeline
- [2026-03-17] decision: WezTerm open-uri handler for linear://, notion://, slack://, figma:// custom protocols
- [2026-03-17] decision: DataTable for PRs (row selection opens PR), Collapsible for completed goals, Sparkline for history (hidden when no data)
- [2026-03-17] decision: bordered panels with CSS border: solid — goals panel blue (#58a6ff), others grey (#30363d)
- [2026-03-17] gotcha: wezterm cli get-text cannot read Textual alternate screen — use --once mode or screencapture for debugging
- [2026-03-17] gotcha: only escape [ not ] in Rich/Textual markup — escaping ] causes literal backslashes
