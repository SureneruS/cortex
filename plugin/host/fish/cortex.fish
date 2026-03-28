# Fish completions for cortex CLI — auto-generated 2026-03-28

complete -c cortex -f

# ── Top-level commands ───────────────────────────────────────
set -l __cortex_cmds brief checkpoint cron daemon dashboard init link pr reindex session status stream tasks team test ui

complete -c cortex -n "not __fish_seen_subcommand_from $__cortex_cmds" -a brief -d "Session brief for hook injection"
complete -c cortex -n "not __fish_seen_subcommand_from $__cortex_cmds" -a checkpoint -d "Weekly checkpoints"
complete -c cortex -n "not __fish_seen_subcommand_from $__cortex_cmds" -a cron -d "Persistent cron jobs"
complete -c cortex -n "not __fish_seen_subcommand_from $__cortex_cmds" -a daemon -d "Background daemon"
complete -c cortex -n "not __fish_seen_subcommand_from $__cortex_cmds" -a dashboard -d "Interactive TUI dashboard"
complete -c cortex -n "not __fish_seen_subcommand_from $__cortex_cmds" -a init -d "Initialize Cortex"
complete -c cortex -n "not __fish_seen_subcommand_from $__cortex_cmds" -a link -d "Link session to stream"
complete -c cortex -n "not __fish_seen_subcommand_from $__cortex_cmds" -a pr -d "GitHub PR operations"
complete -c cortex -n "not __fish_seen_subcommand_from $__cortex_cmds" -a reindex -d "Rebuild vector index"
complete -c cortex -n "not __fish_seen_subcommand_from $__cortex_cmds" -a session -d "Session orchestration"
complete -c cortex -n "not __fish_seen_subcommand_from $__cortex_cmds" -a status -d "Active streams"
complete -c cortex -n "not __fish_seen_subcommand_from $__cortex_cmds" -a stream -d "Work streams"
complete -c cortex -n "not __fish_seen_subcommand_from $__cortex_cmds" -a tasks -d "Pending task backups"
complete -c cortex -n "not __fish_seen_subcommand_from $__cortex_cmds" -a team -d "Team sessions"
complete -c cortex -n "not __fish_seen_subcommand_from $__cortex_cmds" -a test -d "E2E test suites"
complete -c cortex -n "not __fish_seen_subcommand_from $__cortex_cmds" -a ui -d "Web UI"

# ── Helpers: dynamic completions ─────────────────────────────
function __cortex_session_names
    cortex session list --brief 2>/dev/null | python3 -c "import json,sys; [print(s['name']) for s in json.load(sys.stdin) if s.get('status') not in ('completed','dead')]" 2>/dev/null
end

function __cortex_repo_names
    ls ~/workspace/cercli/ 2>/dev/null
end

function __cortex_stream_ids
    cortex stream list 2>/dev/null | python3 -c "import json,sys; [print(s.get('_id','')[:12]) for s in json.load(sys.stdin)]" 2>/dev/null
end

function __cortex_cron_names
    cortex cron list 2>/dev/null | python3 -c "import json,sys; [print(j['name']) for j in json.load(sys.stdin)]" 2>/dev/null
end

function __cortex_github_repos
    printf "cercli/recruitment-backend\ncercli/cercli-backend\ncercli/frontend\ncercli/workflows-backend\ncercli/storage-service\n"
end

# ── tasks ────────────────────────────────────────────────────
complete -c cortex -n "__fish_seen_subcommand_from tasks" -l session-id -r -d "CC session ID"

# ── ui ───────────────────────────────────────────────────────
complete -c cortex -n "__fish_seen_subcommand_from ui" -l dev -d "Hot reload mode"
complete -c cortex -n "__fish_seen_subcommand_from ui" -l port -r -d "API server port"

# ── checkpoint ───────────────────────────────────────────────
set -l __checkpoint_cmds get save
complete -c cortex -n "__fish_seen_subcommand_from checkpoint; and not __fish_seen_subcommand_from $__checkpoint_cmds" -a get -d "Get checkpoint"
complete -c cortex -n "__fish_seen_subcommand_from checkpoint; and not __fish_seen_subcommand_from $__checkpoint_cmds" -a save -d "Save checkpoint"

complete -c cortex -n "__fish_seen_subcommand_from checkpoint; and __fish_seen_subcommand_from get" -l week -r -d "Week identifier"
complete -c cortex -n "__fish_seen_subcommand_from checkpoint; and __fish_seen_subcommand_from save" -l week -r -d "Week (e.g. 2026-W12)"
complete -c cortex -n "__fish_seen_subcommand_from checkpoint; and __fish_seen_subcommand_from save" -l content -r -d "Checkpoint content"
complete -c cortex -n "__fish_seen_subcommand_from checkpoint; and __fish_seen_subcommand_from save" -l stream-ids -r -d "Comma-separated stream IDs"
complete -c cortex -n "__fish_seen_subcommand_from checkpoint; and __fish_seen_subcommand_from save" -l metadata -r -d "JSON metadata"

# ── cron ─────────────────────────────────────────────────────
set -l __cron_cmds create delete list pause resume
complete -c cortex -n "__fish_seen_subcommand_from cron; and not __fish_seen_subcommand_from $__cron_cmds" -a create -d "Create job"
complete -c cortex -n "__fish_seen_subcommand_from cron; and not __fish_seen_subcommand_from $__cron_cmds" -a delete -d "Delete job"
complete -c cortex -n "__fish_seen_subcommand_from cron; and not __fish_seen_subcommand_from $__cron_cmds" -a list -d "List jobs"
complete -c cortex -n "__fish_seen_subcommand_from cron; and not __fish_seen_subcommand_from $__cron_cmds" -a pause -d "Pause job"
complete -c cortex -n "__fish_seen_subcommand_from cron; and not __fish_seen_subcommand_from $__cron_cmds" -a resume -d "Resume job"

complete -c cortex -n "__fish_seen_subcommand_from cron; and __fish_seen_subcommand_from create" -l name -x -d "Unique job name"
complete -c cortex -n "__fish_seen_subcommand_from cron; and __fish_seen_subcommand_from create" -l cron -r -d "5-field cron expression"
complete -c cortex -n "__fish_seen_subcommand_from cron; and __fish_seen_subcommand_from create" -l action -x -a "check-watches command" -d "Action type"
complete -c cortex -n "__fish_seen_subcommand_from cron; and __fish_seen_subcommand_from create" -l args -r -d "JSON action args"

# cron delete/pause/resume take a job name
for cmd in delete pause resume
    complete -c cortex -n "__fish_seen_subcommand_from cron; and __fish_seen_subcommand_from $cmd" -x -a "(__cortex_cron_names)"
end

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

# pr --repo is common across most subcommands
for cmd in state threads checks react reply batch-resolve watch
    complete -c cortex -n "__fish_seen_subcommand_from pr; and __fish_seen_subcommand_from $cmd" -l repo -x -a "(__cortex_github_repos)" -d "owner/repo format"
end
complete -c cortex -n "__fish_seen_subcommand_from pr; and __fish_seen_subcommand_from reply" -l body -r -d "Reply text"
complete -c cortex -n "__fish_seen_subcommand_from pr; and __fish_seen_subcommand_from batch-resolve" -l items -r -d "JSON [{comment_id,thread_id,reaction}]"
complete -c cortex -n "__fish_seen_subcommand_from pr; and __fish_seen_subcommand_from watch" -l message -r -d "Custom notification message"
# pr react REACTION arg
complete -c cortex -n "__fish_seen_subcommand_from pr; and __fish_seen_subcommand_from react" -a "+1 -1" -d "Reaction"

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

# session spawn flags (-x = exclusive: requires value, no file completion)
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from spawn" -l name -r -d "Session name"
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from spawn" -l goal -r -d "Goal metadata"
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from spawn" -l prompt -r -d "Starting prompt"
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from spawn" -l workspace -x -a "default background" -d "Workspace"
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from spawn" -l model -x -a "haiku sonnet opus" -d "Claude model"
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from spawn" -l split -d "Split current pane"
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from spawn" -l resume -r -d "CC session UUID to resume"
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from spawn" -l repo -x -a "(__cortex_repo_names)" -d "Repo name"
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from spawn" -l permission-mode -x -a "plan full" -d "CC mode"
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from spawn" -l effort -x -a "low medium high" -d "CC effort"
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from spawn" -l agent -r -d "CC agent name"
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from spawn" -l allowed-tools -r -d "CC tools (comma-sep)"
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from spawn" -l worktree -r -d "Worktree name"
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from spawn" -l beside -x -a "(__cortex_session_names)" -d "Split beside session"
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from spawn" -l below -x -a "(__cortex_session_names)" -d "Split below session"
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from spawn" -l color -x -a "blue green yellow purple orange pink cyan red" -d "Session color"

# session list flags
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from list" -l status -x -a "active paused hidden dead completed" -d "Filter by status"
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from list" -l runtime -r -d "Filter by runtime"
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from list" -l brief -d "Omit events/watch"
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from list" -l limit -r -d "Max sessions"

# session close flags
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from close" -l force -d "Skip wrapup"

# session capture flags
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from capture" -l lines -r -d "Scrollback lines"

# session move flags
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from move" -l beside -x -a "(__cortex_session_names)" -d "Move beside"
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from move" -l below -x -a "(__cortex_session_names)" -d "Move below"

# session paint flags
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from paint" -l color -x -a "green red amber blue purple gray" -d "Border color"

# session gather flags
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from gather" -l layout -x -a "tiled even-horizontal even-vertical main-horizontal main-vertical" -d "Layout"

# session layout flags
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from layout" -l window -r -d "Filter window"

# session register flags
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from register" -l data -r -d "JSON fields"
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from register" -l id -r -d "Specific ID"

# session update flags
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from update" -l data -r -d "JSON fields to merge"
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from update" -l trigger -r -d "Update trigger"

# Dynamic session name completions for commands that take a session ref
for cmd in get close pause resume hide show restart send capture move paint auto-close update
    complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from $cmd" -x -a "(__cortex_session_names)"
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

# stream commands that take STREAM_ID as positional arg
for cmd in complete decide get log update
    complete -c cortex -n "__fish_seen_subcommand_from stream; and __fish_seen_subcommand_from $cmd" -x -a "(__cortex_stream_ids)"
end

complete -c cortex -n "__fish_seen_subcommand_from stream; and __fish_seen_subcommand_from create" -l title -r -d "Stream title"
complete -c cortex -n "__fish_seen_subcommand_from stream; and __fish_seen_subcommand_from create" -l repos -x -a "(__cortex_repo_names)" -d "Repos (comma-sep)"
complete -c cortex -n "__fish_seen_subcommand_from stream; and __fish_seen_subcommand_from create" -l metadata -r -d "JSON metadata"

complete -c cortex -n "__fish_seen_subcommand_from stream; and __fish_seen_subcommand_from log" -l content -r -d "Update content"
complete -c cortex -n "__fish_seen_subcommand_from stream; and __fish_seen_subcommand_from log" -l summary -r -d "Short summary"
complete -c cortex -n "__fish_seen_subcommand_from stream; and __fish_seen_subcommand_from log" -l metadata -r -d "JSON metadata"

complete -c cortex -n "__fish_seen_subcommand_from stream; and __fish_seen_subcommand_from decide" -l what -r -d "What was decided"
complete -c cortex -n "__fish_seen_subcommand_from stream; and __fish_seen_subcommand_from decide" -l why -r -d "Why this decision"
complete -c cortex -n "__fish_seen_subcommand_from stream; and __fish_seen_subcommand_from decide" -l metadata -r -d "JSON metadata"

complete -c cortex -n "__fish_seen_subcommand_from stream; and __fish_seen_subcommand_from complete" -l summary -r -d "Completion summary"

complete -c cortex -n "__fish_seen_subcommand_from stream; and __fish_seen_subcommand_from list" -l status -x -a "active completed all" -d "Filter"

complete -c cortex -n "__fish_seen_subcommand_from stream; and __fish_seen_subcommand_from delete" -l type -x -a "stream update decision" -d "Entry type"

complete -c cortex -n "__fish_seen_subcommand_from stream; and __fish_seen_subcommand_from edit" -l type -x -a "update decision" -d "Entry type"
complete -c cortex -n "__fish_seen_subcommand_from stream; and __fish_seen_subcommand_from edit" -l content -r -d "New content"
complete -c cortex -n "__fish_seen_subcommand_from stream; and __fish_seen_subcommand_from edit" -l summary -r -d "New summary"
complete -c cortex -n "__fish_seen_subcommand_from stream; and __fish_seen_subcommand_from edit" -l what -r -d "New what"
complete -c cortex -n "__fish_seen_subcommand_from stream; and __fish_seen_subcommand_from edit" -l why -r -d "New why"
complete -c cortex -n "__fish_seen_subcommand_from stream; and __fish_seen_subcommand_from edit" -l metadata -r -d "JSON metadata"

complete -c cortex -n "__fish_seen_subcommand_from stream; and __fish_seen_subcommand_from update" -l title -r -d "New title"
complete -c cortex -n "__fish_seen_subcommand_from stream; and __fish_seen_subcommand_from update" -l status -x -a "active completed" -d "New status"
complete -c cortex -n "__fish_seen_subcommand_from stream; and __fish_seen_subcommand_from update" -l repos -r -d "Repos (comma-sep)"
complete -c cortex -n "__fish_seen_subcommand_from stream; and __fish_seen_subcommand_from update" -l summary -r -d "New summary"
complete -c cortex -n "__fish_seen_subcommand_from stream; and __fish_seen_subcommand_from update" -l metadata -r -d "JSON metadata"
complete -c cortex -n "__fish_seen_subcommand_from stream; and __fish_seen_subcommand_from update" -l replace-metadata -d "Replace instead of merge"

complete -c cortex -n "__fish_seen_subcommand_from stream; and __fish_seen_subcommand_from link" -l repo -x -a "(__cortex_repo_names)" -d "Repository name"
complete -c cortex -n "__fish_seen_subcommand_from stream; and __fish_seen_subcommand_from link" -l branch -r -d "Branch name"

# ── team ─────────────────────────────────────────────────────
set -l __team_cmds attach kill message messages spawn status
complete -c cortex -n "__fish_seen_subcommand_from team; and not __fish_seen_subcommand_from $__team_cmds" -a attach -d "Jump to pane"
complete -c cortex -n "__fish_seen_subcommand_from team; and not __fish_seen_subcommand_from $__team_cmds" -a kill -d "Kill team session"
complete -c cortex -n "__fish_seen_subcommand_from team; and not __fish_seen_subcommand_from $__team_cmds" -a message -d "Send message"
complete -c cortex -n "__fish_seen_subcommand_from team; and not __fish_seen_subcommand_from $__team_cmds" -a messages -d "View messages"
complete -c cortex -n "__fish_seen_subcommand_from team; and not __fish_seen_subcommand_from $__team_cmds" -a spawn -d "Spawn team session"
complete -c cortex -n "__fish_seen_subcommand_from team; and not __fish_seen_subcommand_from $__team_cmds" -a status -d "Team status"

complete -c cortex -n "__fish_seen_subcommand_from team; and __fish_seen_subcommand_from spawn" -l task -r -d "Task description"
complete -c cortex -n "__fish_seen_subcommand_from team; and __fish_seen_subcommand_from spawn" -l prompt -r -d "Task instructions"
complete -c cortex -n "__fish_seen_subcommand_from team; and __fish_seen_subcommand_from spawn" -l repo -x -a "(__cortex_repo_names)" -d "Repo name"

complete -c cortex -n "__fish_seen_subcommand_from team; and __fish_seen_subcommand_from message" -l thread-id -r -d "Thread ID"

complete -c cortex -n "__fish_seen_subcommand_from team; and __fish_seen_subcommand_from messages" -l to -r -d "Filter recipient"
complete -c cortex -n "__fish_seen_subcommand_from team; and __fish_seen_subcommand_from messages" -l limit -r -d "Max messages"

# team attach/kill/message take session name as positional
for cmd in attach kill message
    complete -c cortex -n "__fish_seen_subcommand_from team; and __fish_seen_subcommand_from $cmd" -x -a "(__cortex_session_names)"
end

# ── test ─────────────────────────────────────────────────────
set -l __test_cmds list run smoke
complete -c cortex -n "__fish_seen_subcommand_from test; and not __fish_seen_subcommand_from $__test_cmds" -a list -d "List suites"
complete -c cortex -n "__fish_seen_subcommand_from test; and not __fish_seen_subcommand_from $__test_cmds" -a run -d "Run suite"
complete -c cortex -n "__fish_seen_subcommand_from test; and not __fish_seen_subcommand_from $__test_cmds" -a smoke -d "Smoke checklist"
