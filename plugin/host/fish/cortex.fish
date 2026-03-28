# Fish completions for cortex CLI — auto-generated
# Run: uv run python scripts/gen-fish-completions.py > plugin/host/fish/cortex.fish

complete -c cortex -f

# ── Helpers ──────────────────────────────────────────────────
function __cortex_session_names
    cortex session list --brief 2>/dev/null | python3 -c "import json,sys; [print(s['name']) for s in json.load(sys.stdin) if s.get('status') not in ('completed','dead')]" 2>/dev/null
end

function __cortex_repo_names
    ls ~/workspace/cercli/ 2>/dev/null
end

function __cortex_stream_ids
    uv run python3 -c "
from pymongo import MongoClient
for s in MongoClient('mongodb://localhost:27017').cortex.streams.find({'status':'active'},{'_id':1,'title':1}):
    print(s['_id'] + '\t' + s.get('title',''))
" 2>/dev/null
end

function __cortex_cron_names
    cortex cron list 2>/dev/null | python3 -c "import json,sys; [print(j['name']) for j in json.load(sys.stdin)]" 2>/dev/null
end

function __cortex_github_repos
    printf "cercli/recruitment-backend\ncercli/cercli-backend\ncercli/frontend\ncercli/workflows-backend\ncercli/storage-service\n"
end

# ── Top-level commands ────────────────────────────────────────
set -l __cortex_cmds brief checkpoint control cron daemon dashboard init link pr reindex session status stream tasks team test ui

complete -c cortex -n "not __fish_seen_subcommand_from $__cortex_cmds" -a brief -d "Print compact session brief (for hook injection)"
complete -c cortex -n "not __fish_seen_subcommand_from $__cortex_cmds" -a checkpoint -d "Manage weekly checkpoints"
complete -c cortex -n "not __fish_seen_subcommand_from $__cortex_cmds" -a control -d "Open the control session"
complete -c cortex -n "not __fish_seen_subcommand_from $__cortex_cmds" -a cron -d "Manage persistent cron jobs"
complete -c cortex -n "not __fish_seen_subcommand_from $__cortex_cmds" -a daemon -d "Manage the Cortex background daemon"
complete -c cortex -n "not __fish_seen_subcommand_from $__cortex_cmds" -a dashboard -d "Open the interactive TUI dashboard"
complete -c cortex -n "not __fish_seen_subcommand_from $__cortex_cmds" -a init -d "Initialize Cortex: create config, DB, and scan repos for context"
complete -c cortex -n "not __fish_seen_subcommand_from $__cortex_cmds" -a link -d "Link a session to a stream"
complete -c cortex -n "not __fish_seen_subcommand_from $__cortex_cmds" -a pr -d "GitHub PR operations"
complete -c cortex -n "not __fish_seen_subcommand_from $__cortex_cmds" -a reindex -d "Rebuild vector embedding index"
complete -c cortex -n "not __fish_seen_subcommand_from $__cortex_cmds" -a session -d "Manage Claude Code sessions"
complete -c cortex -n "not __fish_seen_subcommand_from $__cortex_cmds" -a status -d "Show active Cortex streams"
complete -c cortex -n "not __fish_seen_subcommand_from $__cortex_cmds" -a stream -d "Manage work streams, updates, and decisions"
complete -c cortex -n "not __fish_seen_subcommand_from $__cortex_cmds" -a tasks -d "Print pending task backups for session restore"
complete -c cortex -n "not __fish_seen_subcommand_from $__cortex_cmds" -a team -d "[Deprecated] Use 'cortex session' instead"
complete -c cortex -n "not __fish_seen_subcommand_from $__cortex_cmds" -a test -d "Run E2E test suites"
complete -c cortex -n "not __fish_seen_subcommand_from $__cortex_cmds" -a ui -d "Open the Cortex web UI"

# ── link ──

# ── tasks ──
complete -c cortex -n "__fish_seen_subcommand_from tasks" -l session-id -r -d "Claude Code session ID to restore tasks for."

# ── ui ──
complete -c cortex -n "__fish_seen_subcommand_from ui" -l dev -d "Start dev servers with hot reload"
complete -c cortex -n "__fish_seen_subcommand_from ui" -l port -r -d "API server port"

# ── checkpoint ──────────────────────────────────────────────
set -l __checkpoint_cmds get save
complete -c cortex -n "__fish_seen_subcommand_from checkpoint; and not __fish_seen_subcommand_from $__checkpoint_cmds" -a get -d "Get a checkpoint (latest or specific ..."
complete -c cortex -n "__fish_seen_subcommand_from checkpoint; and not __fish_seen_subcommand_from $__checkpoint_cmds" -a save -d "Save or update a weekly checkpoint"

complete -c cortex -n "__fish_seen_subcommand_from checkpoint; and __fish_seen_subcommand_from get" -l week -r -d "Week identifier (latest if omitted)"
complete -c cortex -n "__fish_seen_subcommand_from checkpoint; and __fish_seen_subcommand_from save" -l week -r -d "Week identifier (e.g. 2026-W12)"
complete -c cortex -n "__fish_seen_subcommand_from checkpoint; and __fish_seen_subcommand_from save" -l content -r -d "Checkpoint content"
complete -c cortex -n "__fish_seen_subcommand_from checkpoint; and __fish_seen_subcommand_from save" -l stream-ids -r -d "Comma-separated stream IDs"
complete -c cortex -n "__fish_seen_subcommand_from checkpoint; and __fish_seen_subcommand_from save" -l metadata -r -d "JSON metadata"

# ── cron ──────────────────────────────────────────────
set -l __cron_cmds create delete list pause resume
complete -c cortex -n "__fish_seen_subcommand_from cron; and not __fish_seen_subcommand_from $__cron_cmds" -a create -d "Create a cron job"
complete -c cortex -n "__fish_seen_subcommand_from cron; and not __fish_seen_subcommand_from $__cron_cmds" -a delete -d "Delete a cron job"
complete -c cortex -n "__fish_seen_subcommand_from cron; and not __fish_seen_subcommand_from $__cron_cmds" -a list -d "List all cron jobs"
complete -c cortex -n "__fish_seen_subcommand_from cron; and not __fish_seen_subcommand_from $__cron_cmds" -a pause -d "Pause a cron job"
complete -c cortex -n "__fish_seen_subcommand_from cron; and not __fish_seen_subcommand_from $__cron_cmds" -a resume -d "Resume a paused cron job"

complete -c cortex -n "__fish_seen_subcommand_from cron; and __fish_seen_subcommand_from create" -l name -r -d "Unique job name"
complete -c cortex -n "__fish_seen_subcommand_from cron; and __fish_seen_subcommand_from create" -l cron -r -d "5-field cron expression"
complete -c cortex -n "__fish_seen_subcommand_from cron; and __fish_seen_subcommand_from create" -l action -x -a "check-watches command" -d "Action type (check-watches, command)"
complete -c cortex -n "__fish_seen_subcommand_from cron; and __fish_seen_subcommand_from create" -l args -r -d "JSON action args"

# cron commands that take job name as positional arg
for cmd in delete pause resume
    complete -c cortex -n "__fish_seen_subcommand_from cron; and __fish_seen_subcommand_from $cmd" -x -a "(__cortex_cron_names)"
end

# ── daemon ──────────────────────────────────────────────
set -l __daemon_cmds run start status stop
complete -c cortex -n "__fish_seen_subcommand_from daemon; and not __fish_seen_subcommand_from $__daemon_cmds" -a run -d "Run the daemon loop (used internally ..."
complete -c cortex -n "__fish_seen_subcommand_from daemon; and not __fish_seen_subcommand_from $__daemon_cmds" -a start -d "Start the daemon in a tmux window"
complete -c cortex -n "__fish_seen_subcommand_from daemon; and not __fish_seen_subcommand_from $__daemon_cmds" -a status -d "Check if the daemon is running"
complete -c cortex -n "__fish_seen_subcommand_from daemon; and not __fish_seen_subcommand_from $__daemon_cmds" -a stop -d "Stop the daemon"


# ── pr ──────────────────────────────────────────────
set -l __pr_cmds batch-resolve checks react reply resolve state threads watch
complete -c cortex -n "__fish_seen_subcommand_from pr; and not __fish_seen_subcommand_from $__pr_cmds" -a batch-resolve -d "React to and resolve multiple PR threads"
complete -c cortex -n "__fish_seen_subcommand_from pr; and not __fish_seen_subcommand_from $__pr_cmds" -a checks -d "Get CI check details for a PR"
complete -c cortex -n "__fish_seen_subcommand_from pr; and not __fish_seen_subcommand_from $__pr_cmds" -a react -d "React to a PR review comment (+1 or -1)"
complete -c cortex -n "__fish_seen_subcommand_from pr; and not __fish_seen_subcommand_from $__pr_cmds" -a reply -d "Reply to a PR review comment"
complete -c cortex -n "__fish_seen_subcommand_from pr; and not __fish_seen_subcommand_from $__pr_cmds" -a resolve -d "Resolve a PR review thread"
complete -c cortex -n "__fish_seen_subcommand_from pr; and not __fish_seen_subcommand_from $__pr_cmds" -a state -d "Get PR state summary"
complete -c cortex -n "__fish_seen_subcommand_from pr; and not __fish_seen_subcommand_from $__pr_cmds" -a threads -d "List PR review threads"
complete -c cortex -n "__fish_seen_subcommand_from pr; and not __fish_seen_subcommand_from $__pr_cmds" -a watch -d "Register a session to watch a PR for ..."

complete -c cortex -n "__fish_seen_subcommand_from pr; and __fish_seen_subcommand_from batch-resolve" -l items -r -d "JSON array of {comment_id, thread_id,..."
complete -c cortex -n "__fish_seen_subcommand_from pr; and __fish_seen_subcommand_from batch-resolve" -l repo -x -a "(__cortex_github_repos)" -d "Repository in owner/repo format"
complete -c cortex -n "__fish_seen_subcommand_from pr; and __fish_seen_subcommand_from checks" -l repo -x -a "(__cortex_github_repos)" -d "Repository in owner/repo format"
complete -c cortex -n "__fish_seen_subcommand_from pr; and __fish_seen_subcommand_from react" -l repo -x -a "(__cortex_github_repos)" -d "Repository in owner/repo format"
complete -c cortex -n "__fish_seen_subcommand_from pr; and __fish_seen_subcommand_from reply" -l body -r -d "Reply text"
complete -c cortex -n "__fish_seen_subcommand_from pr; and __fish_seen_subcommand_from reply" -l repo -x -a "(__cortex_github_repos)" -d "Repository in owner/repo format"
complete -c cortex -n "__fish_seen_subcommand_from pr; and __fish_seen_subcommand_from state" -l repo -x -a "(__cortex_github_repos)" -d "Repository in owner/repo format"
complete -c cortex -n "__fish_seen_subcommand_from pr; and __fish_seen_subcommand_from threads" -l repo -x -a "(__cortex_github_repos)" -d "Repository in owner/repo format"
complete -c cortex -n "__fish_seen_subcommand_from pr; and __fish_seen_subcommand_from watch" -l repo -x -a "(__cortex_github_repos)" -d "Repository in owner/repo format"
complete -c cortex -n "__fish_seen_subcommand_from pr; and __fish_seen_subcommand_from watch" -l message -r -d "Custom message for when changes detected"

# ── session ──────────────────────────────────────────────
set -l __session_cmds attach auto-close capture cleanup close gather get health hide layout list message messages move paint pause register restart resume scatter show spawn update
complete -c cortex -n "__fish_seen_subcommand_from session; and not __fish_seen_subcommand_from $__session_cmds" -a attach -d "Jump to a session's tmux pane"
complete -c cortex -n "__fish_seen_subcommand_from session; and not __fish_seen_subcommand_from $__session_cmds" -a auto-close -d "Close a session by its tmux pane_id (..."
complete -c cortex -n "__fish_seen_subcommand_from session; and not __fish_seen_subcommand_from $__session_cmds" -a capture -d "Capture terminal output from a sessio..."
complete -c cortex -n "__fish_seen_subcommand_from session; and not __fish_seen_subcommand_from $__session_cmds" -a cleanup -d "Close all active sessions with dead t..."
complete -c cortex -n "__fish_seen_subcommand_from session; and not __fish_seen_subcommand_from $__session_cmds" -a close -d "Close a session with channels-first w..."
complete -c cortex -n "__fish_seen_subcommand_from session; and not __fish_seen_subcommand_from $__session_cmds" -a gather -d "Gather sessions into a single window ..."
complete -c cortex -n "__fish_seen_subcommand_from session; and not __fish_seen_subcommand_from $__session_cmds" -a get -d "Get a session by ID, name, or ID prefix"
complete -c cortex -n "__fish_seen_subcommand_from session; and not __fish_seen_subcommand_from $__session_cmds" -a health -d "Comprehensive health check"
complete -c cortex -n "__fish_seen_subcommand_from session; and not __fish_seen_subcommand_from $__session_cmds" -a hide -d "Move a session to the background work..."
complete -c cortex -n "__fish_seen_subcommand_from session; and not __fish_seen_subcommand_from $__session_cmds" -a layout -d "Show spatial layout of all panes with..."
complete -c cortex -n "__fish_seen_subcommand_from session; and not __fish_seen_subcommand_from $__session_cmds" -a list -d "List registered sessions. Shows activ..."
complete -c cortex -n "__fish_seen_subcommand_from session; and not __fish_seen_subcommand_from $__session_cmds" -a message -d "Send a message to a session via channels"
complete -c cortex -n "__fish_seen_subcommand_from session; and not __fish_seen_subcommand_from $__session_cmds" -a messages -d "View recent inter-session messages"
complete -c cortex -n "__fish_seen_subcommand_from session; and not __fish_seen_subcommand_from $__session_cmds" -a move -d "Move a session's pane beside or below..."
complete -c cortex -n "__fish_seen_subcommand_from session; and not __fish_seen_subcommand_from $__session_cmds" -a paint -d "Set tmux pane border colors. Without ..."
complete -c cortex -n "__fish_seen_subcommand_from session; and not __fish_seen_subcommand_from $__session_cmds" -a pause -d "Pause a session"
complete -c cortex -n "__fish_seen_subcommand_from session; and not __fish_seen_subcommand_from $__session_cmds" -a register -d "Register a new session in the Cortex ..."
complete -c cortex -n "__fish_seen_subcommand_from session; and not __fish_seen_subcommand_from $__session_cmds" -a restart -d "Restart CC"
complete -c cortex -n "__fish_seen_subcommand_from session; and not __fish_seen_subcommand_from $__session_cmds" -a resume -d "Resume a paused session"
complete -c cortex -n "__fish_seen_subcommand_from session; and not __fish_seen_subcommand_from $__session_cmds" -a scatter -d "Break sessions into separate windows ..."
complete -c cortex -n "__fish_seen_subcommand_from session; and not __fish_seen_subcommand_from $__session_cmds" -a show -d "Bring a hidden session back from back..."
complete -c cortex -n "__fish_seen_subcommand_from session; and not __fish_seen_subcommand_from $__session_cmds" -a spawn -d "Spawn a new Claude Code session in a ..."
complete -c cortex -n "__fish_seen_subcommand_from session; and not __fish_seen_subcommand_from $__session_cmds" -a update -d "Update a session's fields"

complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from capture" -l lines -r -d "Number of scrollback lines to capture"
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from close" -l force -d "Skip wrapup and close immediately"
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from gather" -l layout -x -a "tiled even-horizontal even-vertical main-horizontal main-vertical" -d "Layout: tiled, even-horizontal, etc."
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from layout" -l window -r -d "Filter to a specific window name or i..."
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from list" -l status -x -a "active paused hidden dead completed" -d "Filter by status"
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from list" -l runtime -r -d "Filter by runtime state"
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from list" -l brief -d "Omit events and watch details"
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from list" -l limit -r -d "Max sessions to return"
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from message" -l thread-id -r -d "Thread ID for conversation linking"
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from messages" -l to -r -d "Filter by recipient"
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from messages" -l limit -r -d "Max messages"
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from move" -l beside -x -a "(__cortex_session_names)" -d "Move beside this session (horizontal)"
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from move" -l below -x -a "(__cortex_session_names)" -d "Move below this session (vertical)"
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from paint" -l color -x -a "green red amber blue purple gray" -d "Color name or #hex"
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from register" -l data -r -d "JSON object of fields to set on the n..."
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from register" -l id -r -d "Use a specific ID"
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from spawn" -l name -r -d "Session name"
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from spawn" -l goal -r -d "Registry metadata describing the sess..."
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from spawn" -l prompt -r -d "Prompt to send to the session after i..."
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from spawn" -l workspace -x -a "default background" -d "Workspace (default or background)"
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from spawn" -l model -x -a "haiku sonnet opus" -d "Claude model (e.g. haiku, sonnet, opus)"
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from spawn" -l split -d "Split current pane horizontally inste..."
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from spawn" -l resume -r -d "CC session UUID to resume"
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from spawn" -l repo -x -a "(__cortex_repo_names)" -d "Repo name under ~/workspace/cercli/ t..."
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from spawn" -l permission-mode -x -a "plan full" -d "CC permission mode (e.g. plan, full)"
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from spawn" -l effort -x -a "low medium high" -d "CC effort level (e.g. low, medium, high)"
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from spawn" -l agent -r -d "CC agent name to use"
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from spawn" -l allowed-tools -r -d "CC allowed tools (comma-separated)"
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from spawn" -l worktree -r -d "CC worktree name"
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from spawn" -l beside -x -a "(__cortex_session_names)" -d "Split horizontally beside this sessio..."
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from spawn" -l below -x -a "(__cortex_session_names)" -d "Split vertically below this session/pane"
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from spawn" -l color -x -a "blue green yellow purple orange pink cyan red" -d "CC session color"
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from update" -l data -r -d "JSON object of fields to merge"
complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from update" -l trigger -r -d "What triggered this update"

# session commands that take session name as positional arg
for cmd in get close pause resume hide show restart capture move paint auto-close update attach message messages
    complete -c cortex -n "__fish_seen_subcommand_from session; and __fish_seen_subcommand_from $cmd" -x -a "(__cortex_session_names)"
end

# ── stream ──────────────────────────────────────────────
set -l __stream_cmds complete create decide delete edit get link list log search update
complete -c cortex -n "__fish_seen_subcommand_from stream; and not __fish_seen_subcommand_from $__stream_cmds" -a complete -d "Mark a stream as completed"
complete -c cortex -n "__fish_seen_subcommand_from stream; and not __fish_seen_subcommand_from $__stream_cmds" -a create -d "Create a new stream"
complete -c cortex -n "__fish_seen_subcommand_from stream; and not __fish_seen_subcommand_from $__stream_cmds" -a decide -d "Log a decision to a stream"
complete -c cortex -n "__fish_seen_subcommand_from stream; and not __fish_seen_subcommand_from $__stream_cmds" -a delete -d "Delete a stream, update, or decision"
complete -c cortex -n "__fish_seen_subcommand_from stream; and not __fish_seen_subcommand_from $__stream_cmds" -a edit -d "Edit an existing update or decision"
complete -c cortex -n "__fish_seen_subcommand_from stream; and not __fish_seen_subcommand_from $__stream_cmds" -a get -d "Get full stream context (updates, dec..."
complete -c cortex -n "__fish_seen_subcommand_from stream; and not __fish_seen_subcommand_from $__stream_cmds" -a link -d "Link a session to a stream"
complete -c cortex -n "__fish_seen_subcommand_from stream; and not __fish_seen_subcommand_from $__stream_cmds" -a list -d "List streams"
complete -c cortex -n "__fish_seen_subcommand_from stream; and not __fish_seen_subcommand_from $__stream_cmds" -a log -d "Log a progress update to a stream"
complete -c cortex -n "__fish_seen_subcommand_from stream; and not __fish_seen_subcommand_from $__stream_cmds" -a search -d "Search across updates, decisions, and..."
complete -c cortex -n "__fish_seen_subcommand_from stream; and not __fish_seen_subcommand_from $__stream_cmds" -a update -d "Update a stream"

complete -c cortex -n "__fish_seen_subcommand_from stream; and __fish_seen_subcommand_from complete" -l summary -r -d "Completion summary"
complete -c cortex -n "__fish_seen_subcommand_from stream; and __fish_seen_subcommand_from create" -l title -r -d "Stream title"
complete -c cortex -n "__fish_seen_subcommand_from stream; and __fish_seen_subcommand_from create" -l repos -x -a "(__cortex_repo_names)" -d "Comma-separated repo names"
complete -c cortex -n "__fish_seen_subcommand_from stream; and __fish_seen_subcommand_from create" -l metadata -r -d "JSON metadata"
complete -c cortex -n "__fish_seen_subcommand_from stream; and __fish_seen_subcommand_from decide" -l what -r -d "What was decided"
complete -c cortex -n "__fish_seen_subcommand_from stream; and __fish_seen_subcommand_from decide" -l why -r -d "Why this decision"
complete -c cortex -n "__fish_seen_subcommand_from stream; and __fish_seen_subcommand_from decide" -l metadata -r -d "JSON metadata"
complete -c cortex -n "__fish_seen_subcommand_from stream; and __fish_seen_subcommand_from delete" -l type -x -a "stream update decision" -d "type"
complete -c cortex -n "__fish_seen_subcommand_from stream; and __fish_seen_subcommand_from edit" -l type -x -a "update decision" -d "type"
complete -c cortex -n "__fish_seen_subcommand_from stream; and __fish_seen_subcommand_from edit" -l content -r -d "content"
complete -c cortex -n "__fish_seen_subcommand_from stream; and __fish_seen_subcommand_from edit" -l summary -r -d "summary"
complete -c cortex -n "__fish_seen_subcommand_from stream; and __fish_seen_subcommand_from edit" -l what -r -d "what"
complete -c cortex -n "__fish_seen_subcommand_from stream; and __fish_seen_subcommand_from edit" -l why -r -d "why"
complete -c cortex -n "__fish_seen_subcommand_from stream; and __fish_seen_subcommand_from edit" -l metadata -r -d "JSON metadata"
complete -c cortex -n "__fish_seen_subcommand_from stream; and __fish_seen_subcommand_from link" -l repo -x -a "(__cortex_repo_names)" -d "Repository name"
complete -c cortex -n "__fish_seen_subcommand_from stream; and __fish_seen_subcommand_from link" -l branch -r -d "Branch name"
complete -c cortex -n "__fish_seen_subcommand_from stream; and __fish_seen_subcommand_from list" -l status -x -a "active completed all" -d "Filter by status (active|completed|all)"
complete -c cortex -n "__fish_seen_subcommand_from stream; and __fish_seen_subcommand_from log" -l content -r -d "Update content"
complete -c cortex -n "__fish_seen_subcommand_from stream; and __fish_seen_subcommand_from log" -l summary -r -d "Short summary"
complete -c cortex -n "__fish_seen_subcommand_from stream; and __fish_seen_subcommand_from log" -l metadata -r -d "JSON metadata"
complete -c cortex -n "__fish_seen_subcommand_from stream; and __fish_seen_subcommand_from update" -l title -r -d "title"
complete -c cortex -n "__fish_seen_subcommand_from stream; and __fish_seen_subcommand_from update" -l status -x -a "active completed" -d "status"
complete -c cortex -n "__fish_seen_subcommand_from stream; and __fish_seen_subcommand_from update" -l repos -x -a "(__cortex_repo_names)" -d "Comma-separated repo names"
complete -c cortex -n "__fish_seen_subcommand_from stream; and __fish_seen_subcommand_from update" -l summary -r -d "summary"
complete -c cortex -n "__fish_seen_subcommand_from stream; and __fish_seen_subcommand_from update" -l metadata -r -d "JSON metadata"
complete -c cortex -n "__fish_seen_subcommand_from stream; and __fish_seen_subcommand_from update" -l replace-metadata -d "Replace metadata instead of merging"

# stream commands that take STREAM_ID as positional arg
for cmd in complete decide get log update
    complete -c cortex -n "__fish_seen_subcommand_from stream; and __fish_seen_subcommand_from $cmd" -x -a "(__cortex_stream_ids)"
end

# ── team ──────────────────────────────────────────────
set -l __team_cmds kill message spawn
complete -c cortex -n "__fish_seen_subcommand_from team; and not __fish_seen_subcommand_from $__team_cmds" -a kill -d "[Deprecated] Use 'cortex session clos..."
complete -c cortex -n "__fish_seen_subcommand_from team; and not __fish_seen_subcommand_from $__team_cmds" -a message -d "[Deprecated] Use 'cortex session mess..."
complete -c cortex -n "__fish_seen_subcommand_from team; and not __fish_seen_subcommand_from $__team_cmds" -a spawn -d "[Deprecated] Use 'cortex session spaw..."

complete -c cortex -n "__fish_seen_subcommand_from team; and __fish_seen_subcommand_from message" -l thread-id -r -d "thread-id"
complete -c cortex -n "__fish_seen_subcommand_from team; and __fish_seen_subcommand_from spawn" -l task -r -d "task"
complete -c cortex -n "__fish_seen_subcommand_from team; and __fish_seen_subcommand_from spawn" -l prompt -r -d "prompt"
complete -c cortex -n "__fish_seen_subcommand_from team; and __fish_seen_subcommand_from spawn" -l repo -x -a "(__cortex_repo_names)" -d "repo"

# ── test ──────────────────────────────────────────────
set -l __test_cmds list run smoke
complete -c cortex -n "__fish_seen_subcommand_from test; and not __fish_seen_subcommand_from $__test_cmds" -a list -d "List available test suites"
complete -c cortex -n "__fish_seen_subcommand_from test; and not __fish_seen_subcommand_from $__test_cmds" -a run -d "Run a test suite with pre-flight checks"
complete -c cortex -n "__fish_seen_subcommand_from test; and not __fish_seen_subcommand_from $__test_cmds" -a smoke -d "Generate a smoke test checklist for m..."

complete -c cortex -n "__fish_seen_subcommand_from test; and __fish_seen_subcommand_from run" -l verbose -d "Verbose pytest output"
complete -c cortex -n "__fish_seen_subcommand_from test; and __fish_seen_subcommand_from run" -l filter -r -d "pytest -k filter expression"

