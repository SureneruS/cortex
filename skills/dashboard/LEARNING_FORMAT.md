# Learnings Format

The `workspace/learnings.md` file is your persistent memory across sessions. Keep it concise — one line per entry, two max for complex items.

## Sections

```markdown
## Preferences
- [YYYY-MM-DD] preference: description

## Feedback
- [YYYY-MM-DD] type/severity: description — outcome

## Decisions
- [YYYY-MM-DD] decision: what was decided — rationale
```

## Types

| Type | When |
|------|------|
| `bug` | Current output is wrong or broken |
| `improvement` | Current output works but could be better |
| `feature` | Something is missing that should exist |
| `preference` | User expressed a visual/data/interaction preference |
| `observation` | Runtime insight (data source reliability, terminal dimensions, etc.) |

## Severities

| Severity | Meaning |
|----------|---------|
| `critical` | Breaks the dashboard or makes it unusable |
| `normal` | Noticeable issue but dashboard is functional |
| `low` | Cosmetic, edge case, or nice-to-have |

## Examples

```markdown
## Preferences
- [2026-03-16] preference: chose rich as rendering framework
- [2026-03-16] preference: compact density, mono font, no emojis

## Feedback
- [2026-03-16] bug/critical: PR table shows stale data after merge — fixed by adding poll refresh
- [2026-03-16] feature/normal: add Linear ticket status to goals section
- [2026-03-16] improvement/low: badge text too wide at 80col — logged for rebuild

## Decisions
- [2026-03-16] decision: poll PRs every 2min, Cortex via SSE — PRs change infrequently, streams are event-driven
- [2026-03-16] decision: tried textual for interactivity, reverted to rich — startup time too slow for 30s budget
```
