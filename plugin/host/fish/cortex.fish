# Fish completions for cortex CLI
# Symlink to ~/.config/fish/completions/cortex.fish

# Top-level subcommands
set -l cortex_cmds stream checkpoint pr session cron daemon test status brief reindex tasks

complete -c cortex -f
complete -c cortex -n "not __fish_seen_subcommand_from $cortex_cmds" -a stream -d "Manage work streams"
complete -c cortex -n "not __fish_seen_subcommand_from $cortex_cmds" -a checkpoint -d "Weekly checkpoints"
complete -c cortex -n "not __fish_seen_subcommand_from $cortex_cmds" -a pr -d "PR operations"
complete -c cortex -n "not __fish_seen_subcommand_from $cortex_cmds" -a session -d "Session orchestration"
complete -c cortex -n "not __fish_seen_subcommand_from $cortex_cmds" -a cron -d "Cron jobs"
complete -c cortex -n "not __fish_seen_subcommand_from $cortex_cmds" -a daemon -d "Background daemon"
complete -c cortex -n "not __fish_seen_subcommand_from $cortex_cmds" -a test -d "E2E test suites"
complete -c cortex -n "not __fish_seen_subcommand_from $cortex_cmds" -a status -d "Quick status"
complete -c cortex -n "not __fish_seen_subcommand_from $cortex_cmds" -a brief -d "Session brief"

# stream subcommands
set -l stream_cmds list get create update complete log decide edit delete search link
complete -c cortex -n "__fish_seen_subcommand_from stream; and not __fish_seen_subcommand_from $stream_cmds" -a list -d "List streams"
complete -c cortex -n "__fish_seen_subcommand_from stream; and not __fish_seen_subcommand_from $stream_cmds" -a get -d "Get stream context"
complete -c cortex -n "__fish_seen_subcommand_from stream; and not __fish_seen_subcommand_from $stream_cmds" -a create -d "Create stream"
complete -c cortex -n "__fish_seen_subcommand_from stream; and not __fish_seen_subcommand_from $stream_cmds" -a log -d "Log progress"
complete -c cortex -n "__fish_seen_subcommand_from stream; and not __fish_seen_subcommand_from $stream_cmds" -a decide -d "Log decision"
complete -c cortex -n "__fish_seen_subcommand_from stream; and not __fish_seen_subcommand_from $stream_cmds" -a search -d "Search history"

# session subcommands
set -l session_cmds spawn list get update send capture close pause resume hide show restart layout paint gather scatter move health cleanup
complete -c cortex -n "__fish_seen_subcommand_from session; and not __fish_seen_subcommand_from $session_cmds" -a spawn -d "Spawn new session"
complete -c cortex -n "__fish_seen_subcommand_from session; and not __fish_seen_subcommand_from $session_cmds" -a list -d "List sessions"
complete -c cortex -n "__fish_seen_subcommand_from session; and not __fish_seen_subcommand_from $session_cmds" -a get -d "Get session details"
complete -c cortex -n "__fish_seen_subcommand_from session; and not __fish_seen_subcommand_from $session_cmds" -a send -d "Send text to session"
complete -c cortex -n "__fish_seen_subcommand_from session; and not __fish_seen_subcommand_from $session_cmds" -a capture -d "Capture pane output"
complete -c cortex -n "__fish_seen_subcommand_from session; and not __fish_seen_subcommand_from $session_cmds" -a close -d "Close session"
complete -c cortex -n "__fish_seen_subcommand_from session; and not __fish_seen_subcommand_from $session_cmds" -a pause -d "Pause session"
complete -c cortex -n "__fish_seen_subcommand_from session; and not __fish_seen_subcommand_from $session_cmds" -a resume -d "Resume paused session"
complete -c cortex -n "__fish_seen_subcommand_from session; and not __fish_seen_subcommand_from $session_cmds" -a hide -d "Hide to background"
complete -c cortex -n "__fish_seen_subcommand_from session; and not __fish_seen_subcommand_from $session_cmds" -a show -d "Show from background"
complete -c cortex -n "__fish_seen_subcommand_from session; and not __fish_seen_subcommand_from $session_cmds" -a restart -d "Restart CC in pane"
complete -c cortex -n "__fish_seen_subcommand_from session; and not __fish_seen_subcommand_from $session_cmds" -a layout -d "Show pane layout"
complete -c cortex -n "__fish_seen_subcommand_from session; and not __fish_seen_subcommand_from $session_cmds" -a gather -d "Gather panes into window"
complete -c cortex -n "__fish_seen_subcommand_from session; and not __fish_seen_subcommand_from $session_cmds" -a scatter -d "Scatter to separate tabs"
complete -c cortex -n "__fish_seen_subcommand_from session; and not __fish_seen_subcommand_from $session_cmds" -a move -d "Move pane beside/below"
complete -c cortex -n "__fish_seen_subcommand_from session; and not __fish_seen_subcommand_from $session_cmds" -a health -d "Health check"
complete -c cortex -n "__fish_seen_subcommand_from session; and not __fish_seen_subcommand_from $session_cmds" -a cleanup -d "Cleanup dead sessions"

# session spawn flags
complete -c cortex -n "__fish_seen_subcommand_from spawn" -l name -d "Session name"
complete -c cortex -n "__fish_seen_subcommand_from spawn" -l goal -d "Goal description"
complete -c cortex -n "__fish_seen_subcommand_from spawn" -l prompt -d "Starting prompt"
complete -c cortex -n "__fish_seen_subcommand_from spawn" -l repo -d "Repo name" -a "(ls ~/workspace/cercli/)"
complete -c cortex -n "__fish_seen_subcommand_from spawn" -l beside -d "Split beside session"
complete -c cortex -n "__fish_seen_subcommand_from spawn" -l below -d "Split below session"
complete -c cortex -n "__fish_seen_subcommand_from spawn" -l color -d "CC session color" -a "blue green yellow purple orange pink cyan red"
complete -c cortex -n "__fish_seen_subcommand_from spawn" -l model -d "Claude model" -a "haiku sonnet opus"
complete -c cortex -n "__fish_seen_subcommand_from spawn" -l permission-mode -d "CC mode" -a "plan full"
complete -c cortex -n "__fish_seen_subcommand_from spawn" -l effort -d "CC effort" -a "low medium high"
complete -c cortex -n "__fish_seen_subcommand_from spawn" -l worktree -d "Worktree name"
complete -c cortex -n "__fish_seen_subcommand_from spawn" -l resume -d "CC session UUID"

# Dynamic session name completions for commands that take a session ref
for cmd in get close pause resume hide show restart send capture move
    complete -c cortex -n "__fish_seen_subcommand_from $cmd" -a "(cortex session list --brief 2>/dev/null | python3 -c \"import json,sys; [print(s['name']) for s in json.load(sys.stdin) if s.get('status') not in ('completed','dead')]\" 2>/dev/null)"
end

# cron subcommands
complete -c cortex -n "__fish_seen_subcommand_from cron; and not __fish_seen_subcommand_from create list delete pause resume" -a create -d "Create job"
complete -c cortex -n "__fish_seen_subcommand_from cron; and not __fish_seen_subcommand_from create list delete pause resume" -a list -d "List jobs"
complete -c cortex -n "__fish_seen_subcommand_from cron; and not __fish_seen_subcommand_from create list delete pause resume" -a delete -d "Delete job"

# daemon subcommands
complete -c cortex -n "__fish_seen_subcommand_from daemon; and not __fish_seen_subcommand_from start stop status" -a start -d "Start daemon"
complete -c cortex -n "__fish_seen_subcommand_from daemon; and not __fish_seen_subcommand_from start stop status" -a stop -d "Stop daemon"
complete -c cortex -n "__fish_seen_subcommand_from daemon; and not __fish_seen_subcommand_from start stop status" -a status -d "Check status"

# test subcommands
complete -c cortex -n "__fish_seen_subcommand_from test; and not __fish_seen_subcommand_from run list smoke" -a run -d "Run test suite"
complete -c cortex -n "__fish_seen_subcommand_from test; and not __fish_seen_subcommand_from run list smoke" -a list -d "List suites"
complete -c cortex -n "__fish_seen_subcommand_from test; and not __fish_seen_subcommand_from run list smoke" -a smoke -d "Smoke checklist"
complete -c cortex -n "__fish_seen_subcommand_from run smoke" -a "slice-0 slice-1 slice-2 slice-3 slice-4"
