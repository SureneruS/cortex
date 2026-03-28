# Fish completions for cortex CLI — auto-generated 2026-03-28

complete -c cortex -f

# ── Top-level commands ───────────────────────────────────────
set -l __cortex_cmds brief checkpoint cron daemon dashboard init link plugin pr reindex session status stream tasks team test ui

complete -c cortex -n "not __fish_seen_subcommand_from $__cortex_cmds" -a brief -d "Session brief for hook injection"
complete -c cortex -n "not __fish_seen_subcommand_from $__cortex_cmds" -a checkpoint -d "Weekly checkpoints"
complete -c cortex -n "not __fish_seen_subcommand_from $__cortex_cmds" -a cron -d "Persistent cron jobs"
complete -c cortex -n "not __fish_seen_subcommand_from $__cortex_cmds" -a daemon -d "Background daemon"
complete -c cortex -n "not __fish_seen_subcommand_from $__cortex_cmds" -a dashboard -d "Interactive TUI dashboard"
complete -c cortex -n "not __fish_seen_subcommand_from $__cortex_cmds" -a init -d "Initialize Cortex"
complete -c cortex -n "not __fish_seen_subcommand_from $__cortex_cmds" -a link -d "Link session to stream"
complete -c cortex -n "not __fish_seen_subcommand_from $__cortex_cmds" -a plugin -d "Plugin management"
complete -c cortex -n "not __fish_seen_subcommand_from $__cortex_cmds" -a pr -d "GitHub PR operations"
complete -c cortex -n "not __fish_seen_subcommand_from $__cortex_cmds" -a reindex -d "Rebuild vector index"
complete -c cortex -n "not __fish_seen_subcommand_from $__cortex_cmds" -a session -d "Session orchestration"
complete -c cortex -n "not __fish_seen_subcommand_from $__cortex_cmds" -a status -d "Active streams"
complete -c cortex -n "not __fish_seen_subcommand_from $__cortex_cmds" -a stream -d "Work streams"
complete -c cortex -n "not __fish_seen_subcommand_from $__cortex_cmds" -a tasks -d "Pending task backups"
complete -c cortex -n "not __fish_seen_subcommand_from $__cortex_cmds" -a team -d "Team sessions"
complete -c cortex -n "not __fish_seen_subcommand_from $__cortex_cmds" -a test -d "E2E test suites"
complete -c cortex -n "not __fish_seen_subcommand_from $__cortex_cmds" -a ui -d "Web UI"

# ── Helper: active session names ─────────────────────────────
function __cortex_session_names
    cortex session list --brief 2>/dev/null | python3 -c "import json,sys; [print(s['name']) for s in json.load(sys.stdin) if s.get('status') not in ('completed','dead')]" 2>/dev/null
end

function __cortex_repo_names
    ls ~/workspace/cercli/ 2>/dev/null
end

# ── tasks ────────────────────────────────────────────────────
complete -c cortex -n "__fish_seen_subcommand_from tasks" -l session-id -d "CC session ID"

# ── ui ───────────────────────────────────────────────────────
complete -c cortex -n "__fish_seen_subcommand_from ui" -l dev -d "Hot reload mode"
complete -c cortex -n "__fish_seen_subcommand_from ui" -l port -d "API server port"

# ── checkpoint ───────────────────────────────────────────────
set -l __checkpoint_cmds get save
complete -c cortex -n "__fish_seen_subcommand_from checkpoint; and not __fish_seen_subcommand_from $__checkpoint_cmds" -a get -d "Get checkpoint"
complete -c cortex -n "__fish_seen_subcommand_from checkpoint; and not __fish_seen_subcommand_from $__checkpoint_cmds" -a save -d "Save checkpoint"

complete -c cortex -n "__fish_seen_subcommand_from checkpoint; and __fish_seen_subcommand_from get" -l week -d "Week identifier"
complete -c cortex -n "__fish_seen_subcommand_from checkpoint; and __fish_seen_subcommand_from save" -l week -d "Week (e.g. 2026-W12)"
complete -c cortex -n "__fish_seen_subcommand_from checkpoint; and __fish_seen_subcommand_from save" -l content -d "Checkpoint content"
complete -c cortex -n "__fish_seen_subcommand_from checkpoint; and __fish_seen_subcommand_from save" -l stream-ids -d "Comma-separated stream IDs"
complete -c cortex -n "__fish_seen_subcommand_from checkpoint; and __fish_seen_subcommand_from save" -l metadata -d "JSON metadata"

# ── cron ─────────────────────────────────────────────────────
set -l __cron_cmds create delete list pause resume
complete -c cortex -n "__fish_seen_subcommand_from cron; and not __fish_seen_subcommand_from $__cron_cmds" -a create -d "Create job"
complete -c cortex -n "__fish_seen_subcommand_from cron; and not __fish_seen_subcommand_from $__cron_cmds" -a delete -d "Delete job"
complete -c cortex -n "__fish_seen_subcommand_from cron; and not __fish_seen_subcommand_from $__cron_cmds" -a list -d "List jobs"
complete -c cortex -n "__fish_seen_subcommand_from cron; and not __fish_seen_subcommand_from $__cron_cmds" -a pause -d "Pause job"
complete -c cortex -n "__fish_seen_subcommand_from cron; and not __fish_seen_subcommand_from $__cron_cmds" -a resume -d "Resume job"

complete -c cortex -n "__fish_seen_subcommand_from cron; and __fish_seen_subcommand_from create" -l name -d "Unique job name"
complete -c cortex -n "__fish_seen_subcommand_from cron; and __fish_seen_subcommand_from create" -l cron -d "5-field cron expression"
complete -c cortex -n "__fish_seen_subcommand_from cron; and __fish_seen_subcommand_from create" -l action -d "Action type" -a "check-watches command"
complete -c cortex -n "__fish_seen_subcommand_from cron; and __fish_seen_subcommand_from create" -l args -d "JSON action args"

# ── daemon ───────────────────────────────────────────────────
set -l __daemon_cmds run start status stop
complete -c cortex -n "__fish_seen_subcommand_from daemon; and not __fish_seen_subcommand_from $__daemon_cmds" -a run -d "Run loop (internal)"
complete -c cortex -n "__fish_seen_subcommand_from daemon; and not __fish_seen_subcommand_from $__daemon_cmds" -a start -d "Start in tmux"
complete -c cortex -n "__fish_seen_subcommand_from daemon; and not __fish_seen_subcommand_from $__daemon_cmds" -a status -d "Check status"
complete -c cortex -n "__fish_seen_subcommand_from daemon; and not __fish_seen_subcommand_from $__daemon_cmds" -a stop -d "Stop daemon"

# ── pr ───────────────────────────────────────────────────────
set -l __pr_cmds batch-resolve checks react reply resolve state threads watch
complete -c cortex -n "__fish_seen_subcommand_from pr; and not __fish_seen_subcommand_from $__pr_cmds" -a batch-resolve -d "Batch react+resolve threads"
complete -c cortex -n "__fish_seen_subcommand_from pr; and not __fish_seen_subcommand_from $__pr_cmds" -a checks -d "CI check details"
complete -c cortex -n "__fish_seen_subcommand_from pr; and not __fish_seen_subcommand_from $__pr_cmds" -a react -d "React to comment (+1/-1)"
complete -c cortex -n "__fish_seen_subcommand_from pr; and not __fish_seen_subcommand_from $__pr_cmds" -a reply -d "Reply to comment"
complete -c cortex -n "__fish_seen_subcommand_from pr; and not __fish_seen_subcommand_from $__pr_cmds" -a resolve -d "Resolve thread"
complete -c cortex -n "__fish_seen_subcommand_from pr; and not __fish_seen_subcommand_from $__pr_cmds" -a state -d "PR state summary"
complete -c cortex -n "__fish_seen_subcommand_from pr; and not __fish_seen_subcommand_from $__pr_cmds" -a threads -d "List review threads"
complete -c cortex -n "__fish_seen_subcommand_from pr; and not __fish_seen_subcommand_from $__pr_cmds" -a watch -d "Watch PR for changes"

# pr flags (--repo is common)
for cmd in state threads checks react reply batch-resolve watch
    complete -c cortex -n "__fish_seen_subcommand_from pr; and __fish_seen_subcommand_from $cmd" -l repo -d "owner/repo format"
end
complete -c cortex -n "__fish_seen_subcommand_from pr; and __fish_seen_subcommand_from reply" -l body -d "Reply text"
complete -c cortex -n "__fish_seen_subcommand_from pr; and __fish_seen_subcommand_from batch-resolve" -l items -d "JSON [{comment_id,thread_id,reaction}]"
complete -c cortex -n "__fish_seen_subcommand_from pr; and __fish_seen_subcommand_from watch" -l message -d "Custom notification message"

# ── session ──────────────────────────────────────────────────
set -l __session_cmds auto-close capture cleanup close gather get health hide layout list move paint pause register restart resume scatter send show spawn update
complete -c cortex -n "__fish_seen_subcommand_from session; and not __fish_seen_subcommand_from $__session_cmds" -a auto-close -d "Close by pane_id (hooks)"
complete -c cortex -n "__fish_seen_subcommand_from session; and not __fish_seen_subcommand_from $__session_cmds" -a capture -d "Capture pane output"
complete -c cortex -n "__fish_seen_subcommand_from session; and not __fish_seen_subcommand_from $__session_cmds" -a cleanup -d "Cleanup dead sessions"
complete -c cortex -n "__fish_seen_subcommand_from session; and not __fish_seen_subcommand_from $__session_cmds" -a close -d "Close with wrapup"
complete -c cortex -n "__fish_seen_subcommand_from session; and not __fish_seen_subcommand_from $__session_cmds" -a gather -d "Gather into window"
complete -c cortex -n "__fish_seen_subcommand_from session; and not __fish_seen_subcommand_from $__session_cmds" -a get -d "Get session details"
complete -c cortex -n "__fish_seen_subcommand_from session; and not __fish_seen_subcommand_from $__session_cmds" -a health -d "Health check"
complete -c cortex -n "__fish_seen_subcommand_from session; and not __fish_seen_subcommand_from $__session_cmds" -a hide -d "Hide to background"
complete -c cortex -n "__fish_seen_subcommand_from session; and not __fish_seen_subcommand_from $__session_cmds" -a layout -d "Pane layout map"
complete -c cortex -n "__fish_seen_subcommand_from session; and not __fish_seen_subcommand_from $__session_cmds" -a list -d "List sessions"
complete -c cortex -n "__fish_seen_subcommand_from session; and not __fish_seen_subcommand_from $__session_cmds" -a move -d "Move pane beside/below"
complete -c cortex -n "__fish_seen_subcommand_from session; and not __fish_seen_subcommand_from $__session_cmds" -a paint -d "Set pane border color"
complete -c cortex -n "__fish_seen_subcommand_from session; and not __fish_seen_subcommand_from $__session_cmds" -a pause -d "Pause session"
complete -c cortex -n "__fish_seen_subcommand_from session; and not __fish_seen_subcommand_from $__session_cmds" -a register -d "Register in registry"
complete -c cortex -n "__fish_seen_subcommand_from session; and not __fish_seen_subcommand_from $__session_cmds" -a restart -d "Restart CC in pane"
complete -c cortex -n "__fish_seen_subcommand_from session; and not __fish_seen_subcommand_from $__session_cmds" -a resume -d "Resume paused session"
complete -c cortex -n "__fish_seen_subcommand_from session; and not __fish_seen_subcommand_from $__session_cmds" -a scatter -d "Scatter to separate tabs"
complete -c cortex -n "__fish_seen_subcommand_from session; and not __fish_seen_subcommand_from $__session_cmds" -a send -d "Send text to pane"
complete -c cortex -n "__fish_seen_subcommand_from session; and not __fish_seen_subcommand_from $__session_cmds" -a show -d "Show from background"
complete -c cortex -n "__fish_seen_subcommand_from session; and not __fish_seen_subcommand_from $__session_cmds" -a spawn -d "Spawn new session"
complete -c cortex -n "__fish_seen_subcommand_from session; and not __fish_seen_subcommand_from $__session_cmds" -a update -d "Update session fields"

# session spawn flags
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from spawn" -l name -d "Session name"
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from spawn" -l goal -d "Goal metadata"
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from spawn" -l prompt -d "Starting prompt"
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from spawn" -l workspace -d "Workspace" -a "default background"
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from spawn" -l model -d "Claude model" -a "haiku sonnet opus"
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from spawn" -l split -d "Split current pane"
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from spawn" -l resume -d "CC session UUID to resume"
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from spawn" -l repo -d "Repo name" -a "(__cortex_repo_names)"
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from spawn" -l permission-mode -d "CC mode" -a "plan full"
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from spawn" -l effort -d "CC effort" -a "low medium high"
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from spawn" -l agent -d "CC agent name"
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from spawn" -l allowed-tools -d "CC tools (comma-sep)"
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from spawn" -l worktree -d "Worktree name"
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from spawn" -l beside -d "Split beside session" -a "(__cortex_session_names)"
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from spawn" -l below -d "Split below session" -a "(__cortex_session_names)"
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from spawn" -l color -d "Session color" -a "blue green yellow purple orange pink cyan red"

# session list flags
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from list" -l status -d "Filter by status" -a "active paused hidden dead completed"
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from list" -l runtime -d "Filter by runtime"
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from list" -l brief -d "Omit events/watch"
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from list" -l limit -d "Max sessions"

# session close flags
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from close" -l force -d "Skip wrapup"

# session capture flags
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from capture" -l lines -d "Scrollback lines"

# session move flags
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from move" -l beside -d "Move beside" -a "(__cortex_session_names)"
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from move" -l below -d "Move below" -a "(__cortex_session_names)"

# session paint flags
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from paint" -l color -d "Border color" -a "green red amber blue purple gray"

# session gather flags
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from gather" -l layout -d "Layout" -a "tiled even-horizontal even-vertical main-horizontal main-vertical"

# session layout flags
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from layout" -l window -d "Filter window"

# session register flags
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from register" -l data -d "JSON fields"
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from register" -l id -d "Specific ID"

# session update flags
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from update" -l data -d "JSON fields to merge"
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from update" -l trigger -d "Update trigger"

# Dynamic session name completions for commands that take a session ref
for cmd in get close pause resume hide show restart send capture move paint auto-close update
    complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from $cmd" -a "(__cortex_session_names)"
end

# ── stream ───────────────────────────────────────────────────
set -l __stream_cmds complete create decide delete edit get link list log search update
complete -c cortex -n "__fish_seen_subcommand_from stream; and not __fish_seen_subcommand_from $__stream_cmds" -a complete -d "Mark completed"
complete -c cortex -n "__fish_seen_subcommand_from stream; and not __fish_seen_subcommand_from $__stream_cmds" -a create -d "Create stream"
complete -c cortex -n "__fish_seen_subcommand_from stream; and not __fish_seen_subcommand_from $__stream_cmds" -a decide -d "Log decision"
complete -c cortex -n "__fish_seen_subcommand_from stream; and not __fish_seen_subcommand_from $__stream_cmds" -a delete -d "Delete stream/entry"
complete -c cortex -n "__fish_seen_subcommand_from stream; and not __fish_seen_subcommand_from $__stream_cmds" -a edit -d "Edit entry"
complete -c cortex -n "__fish_seen_subcommand_from stream; and not __fish_seen_subcommand_from $__stream_cmds" -a get -d "Full stream context"
complete -c cortex -n "__fish_seen_subcommand_from stream; and not __fish_seen_subcommand_from $__stream_cmds" -a link -d "Link session to stream"
complete -c cortex -n "__fish_seen_subcommand_from stream; and not __fish_seen_subcommand_from $__stream_cmds" -a list -d "List streams"
complete -c cortex -n "__fish_seen_subcommand_from stream; and not __fish_seen_subcommand_from $__stream_cmds" -a log -d "Log progress"
complete -c cortex -n "__fish_seen_subcommand_from stream; and not __fish_seen_subcommand_from $__stream_cmds" -a search -d "Search history"
complete -c cortex -n "__fish_seen_subcommand_from stream; and not __fish_seen_subcommand_from $__stream_cmds" -a update -d "Update stream"

complete -c cortex -n "__fish_seen_subcommand_from stream; and __fish_seen_subcommand_from create" -l title -d "Stream title"
complete -c cortex -n "__fish_seen_subcommand_from stream; and __fish_seen_subcommand_from create" -l repos -d "Repos (comma-sep)" -a "(__cortex_repo_names)"
complete -c cortex -n "__fish_seen_subcommand_from stream; and __fish_seen_subcommand_from create" -l metadata -d "JSON metadata"

complete -c cortex -n "__fish_seen_subcommand_from stream; and __fish_seen_subcommand_from log" -l content -d "Update content"
complete -c cortex -n "__fish_seen_subcommand_from stream; and __fish_seen_subcommand_from log" -l summary -d "Short summary"
complete -c cortex -n "__fish_seen_subcommand_from stream; and __fish_seen_subcommand_from log" -l metadata -d "JSON metadata"

complete -c cortex -n "__fish_seen_subcommand_from stream; and __fish_seen_subcommand_from decide" -l what -d "What was decided"
complete -c cortex -n "__fish_seen_subcommand_from stream; and __fish_seen_subcommand_from decide" -l why -d "Why this decision"
complete -c cortex -n "__fish_seen_subcommand_from stream; and __fish_seen_subcommand_from decide" -l metadata -d "JSON metadata"

complete -c cortex -n "__fish_seen_subcommand_from stream; and __fish_seen_subcommand_from complete" -l summary -d "Completion summary"

complete -c cortex -n "__fish_seen_subcommand_from stream; and __fish_seen_subcommand_from list" -l status -d "Filter" -a "active completed all"

complete -c cortex -n "__fish_seen_subcommand_from stream; and __fish_seen_subcommand_from delete" -l type -d "Entry type" -a "stream update decision"

complete -c cortex -n "__fish_seen_subcommand_from stream; and __fish_seen_subcommand_from edit" -l type -d "Entry type" -a "update decision"
complete -c cortex -n "__fish_seen_subcommand_from stream; and __fish_seen_subcommand_from edit" -l content -d "New content"
complete -c cortex -n "__fish_seen_subcommand_from stream; and __fish_seen_subcommand_from edit" -l summary -d "New summary"
complete -c cortex -n "__fish_seen_subcommand_from stream; and __fish_seen_subcommand_from edit" -l what -d "New what"
complete -c cortex -n "__fish_seen_subcommand_from stream; and __fish_seen_subcommand_from edit" -l why -d "New why"
complete -c cortex -n "__fish_seen_subcommand_from stream; and __fish_seen_subcommand_from edit" -l metadata -d "JSON metadata"

complete -c cortex -n "__fish_seen_subcommand_from stream; and __fish_seen_subcommand_from update" -l title -d "New title"
complete -c cortex -n "__fish_seen_subcommand_from stream; and __fish_seen_subcommand_from update" -l status -d "New status" -a "active completed"
complete -c cortex -n "__fish_seen_subcommand_from stream; and __fish_seen_subcommand_from update" -l repos -d "Repos (comma-sep)"
complete -c cortex -n "__fish_seen_subcommand_from stream; and __fish_seen_subcommand_from update" -l summary -d "New summary"
complete -c cortex -n "__fish_seen_subcommand_from stream; and __fish_seen_subcommand_from update" -l metadata -d "JSON metadata"
complete -c cortex -n "__fish_seen_subcommand_from stream; and __fish_seen_subcommand_from update" -l replace-metadata -d "Replace instead of merge"

complete -c cortex -n "__fish_seen_subcommand_from stream; and __fish_seen_subcommand_from link" -l repo -d "Repository name" -a "(__cortex_repo_names)"
complete -c cortex -n "__fish_seen_subcommand_from stream; and __fish_seen_subcommand_from link" -l branch -d "Branch name"

# ── team ─────────────────────────────────────────────────────
set -l __team_cmds attach kill message messages spawn status
complete -c cortex -n "__fish_seen_subcommand_from team; and not __fish_seen_subcommand_from $__team_cmds" -a attach -d "Jump to pane"
complete -c cortex -n "__fish_seen_subcommand_from team; and not __fish_seen_subcommand_from $__team_cmds" -a kill -d "Kill team session"
complete -c cortex -n "__fish_seen_subcommand_from team; and not __fish_seen_subcommand_from $__team_cmds" -a message -d "Send message"
complete -c cortex -n "__fish_seen_subcommand_from team; and not __fish_seen_subcommand_from $__team_cmds" -a messages -d "View messages"
complete -c cortex -n "__fish_seen_subcommand_from team; and not __fish_seen_subcommand_from $__team_cmds" -a spawn -d "Spawn team session"
complete -c cortex -n "__fish_seen_subcommand_from team; and not __fish_seen_subcommand_from $__team_cmds" -a status -d "Team status"

complete -c cortex -n "__fish_seen_subcommand_from team; and __fish_seen_subcommand_from spawn" -l task -d "Task description"
complete -c cortex -n "__fish_seen_subcommand_from team; and __fish_seen_subcommand_from spawn" -l prompt -d "Task instructions"
complete -c cortex -n "__fish_seen_subcommand_from team; and __fish_seen_subcommand_from spawn" -l repo -d "Repo name" -a "(__cortex_repo_names)"

complete -c cortex -n "__fish_seen_subcommand_from team; and __fish_seen_subcommand_from message" -l thread-id -d "Thread ID"

complete -c cortex -n "__fish_seen_subcommand_from team; and __fish_seen_subcommand_from messages" -l to -d "Filter recipient"
complete -c cortex -n "__fish_seen_subcommand_from team; and __fish_seen_subcommand_from messages" -l limit -d "Max messages"

# ── plugin ───────────────────────────────────────────────────
complete -c cortex -n "__fish_seen_subcommand_from plugin; and not __fish_seen_subcommand_from sync" -a sync -d "Sync source to CC cache"

# ── test ─────────────────────────────────────────────────────
set -l __test_cmds list run smoke
complete -c cortex -n "__fish_seen_subcommand_from test; and not __fish_seen_subcommand_from $__test_cmds" -a list -d "List suites"
complete -c cortex -n "__fish_seen_subcommand_from test; and not __fish_seen_subcommand_from $__test_cmds" -a run -d "Run suite"
complete -c cortex -n "__fish_seen_subcommand_from test; and not __fish_seen_subcommand_from $__test_cmds" -a smoke -d "Smoke checklist"
