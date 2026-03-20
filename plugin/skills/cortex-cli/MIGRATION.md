# MCP → CLI Migration

**All cortex MCP tools now have CLI equivalents. Use CLI via Bash instead of MCP tools.**

## Quick Reference

| Before (MCP) | After (CLI) |
|---|---|
| `mcp__cortex__cortex_get_active_streams` | `cortex stream list` |
| `mcp__cortex__cortex_get_stream_context(id)` | `cortex stream get <id>` |
| `mcp__cortex__cortex_create_stream(...)` | `cortex stream create --title "..." --repos r1,r2` |
| `mcp__cortex__cortex_update_stream(...)` | `cortex stream update <id> [--title] [--status] ...` |
| `mcp__cortex__cortex_complete_stream(id, summary)` | `cortex stream complete <id> --summary "..."` |
| `mcp__cortex__cortex_log_update(...)` | `cortex stream log <id> --content "..." --summary "..."` |
| `mcp__cortex__cortex_log_decision(...)` | `cortex stream decide <id> --what "..." --why "..."` |
| `mcp__cortex__cortex_edit_entry(...)` | `cortex stream edit <id> --type update\|decision ...` |
| `mcp__cortex__cortex_delete_entry(...)` | `cortex stream delete <id> --type stream\|update\|decision` |
| `mcp__cortex__cortex_link_session(...)` | `cortex stream link <session_id> <stream_id>` |
| `mcp__cortex__cortex_get_context(topic)` | `cortex stream search "<topic>"` |
| `mcp__cortex__cortex_search_history(query)` | `cortex stream search "<query>"` |
| `mcp__cortex__cortex_save_checkpoint(...)` | `cortex checkpoint save --week W --content "..."` |
| `mcp__cortex__cortex_get_checkpoint(...)` | `cortex checkpoint get [--week W]` |
| `mcp__cortex__cortex_get_session_brief` | `cortex brief` |
| `mcp__cortex__cortex_session_spawn(...)` | `cortex session spawn --name N [--goal] [--prompt]` |
| `mcp__cortex__cortex_session_list(...)` | `cortex session list [--status] [--brief]` |
| `mcp__cortex__cortex_session_get(id)` | `cortex session get <id>` |
| `mcp__cortex__cortex_session_update(...)` | `cortex session update <id> --data '{...}'` |
| `mcp__cortex__cortex_session_send(...)` | `cortex session send <id> "<text>"` |
| `mcp__cortex__cortex_session_capture(...)` | `cortex session capture <id>` |
| `mcp__cortex__cortex_session_close(...)` | `cortex session close <id> [--force]` |
| `mcp__cortex__cortex_session_health` | `cortex session health` |
| `mcp__cortex__cortex_session_cleanup` | `cortex session cleanup` |
| `mcp__cortex__cortex_pr_state(...)` | `cortex pr state <n> [--repo o/r]` |
| `mcp__cortex__cortex_pr_threads(...)` | `cortex pr threads <n> [--repo o/r]` |
| `mcp__cortex__cortex_pr_checks(...)` | `cortex pr checks <n> [--repo o/r]` |
| `mcp__cortex__cortex_pr_react(...)` | `cortex pr react <n> <cid> <reaction>` |
| `mcp__cortex__cortex_pr_resolve(...)` | `cortex pr resolve <thread_id>` |
| `mcp__cortex__cortex_pr_batch_resolve(...)` | `cortex pr batch-resolve --items '[...]'` |
| `mcp__cortex__cortex_pr_reply(...)` | `cortex pr reply <n> <cid> --body "..."` |
| `mcp__cortex__cortex_pr_watch(...)` | `cortex pr watch <n> <sid> [--repo o/r]` |
| `mcp__cortex__cortex_cron_create(...)` | `cortex cron create --name N --cron "..." --action A` |
| `mcp__cortex__cortex_cron_list` | `cortex cron list` |
| `mcp__cortex__cortex_cron_delete(name)` | `cortex cron delete <name>` |
| `mcp__cortex__cortex_cron_pause(name)` | `cortex cron pause <name>` |
| `mcp__cortex__cortex_cron_resume(name)` | `cortex cron resume <name>` |
| `mcp__cortex__cortex_daemon_start` | `cortex daemon start` |
| `mcp__cortex__cortex_daemon_stop` | `cortex daemon stop` |
| `mcp__cortex__cortex_daemon_status` | `cortex daemon status` |

## Why CLI?

- Saves ~3k tokens per session (no MCP tool definitions loaded)
- Same functionality, JSON output
- Skills document all commands — invoke `/cortex-cli` for full reference
