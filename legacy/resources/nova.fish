# Fish shell completions for nova

# Helper: list active tmux window names
function __nova_sessions
    tmux list-windows -t sessions -F '#{window_name}' 2>/dev/null
end

# Helper: list sessions with Slack threads (from state.json)
function __nova_slack_sessions
    python3 -c "
import json, pathlib
sf = pathlib.Path.home() / '.nova' / 'state.json'
if not sf.exists(): exit()
state = json.loads(sf.read_text())
for s in state.get('sessions', {}).values():
    w = s.get('tmux_window', '')
    if w and s.get('slack_thread_ts'):
        print(w)
" 2>/dev/null
end

# Helper: list available claude agents
function __nova_agents
    ls ~/.claude/agents/ 2>/dev/null
end

# Helper: list repos in common locations
function __nova_repos
    for d in ~/workspace/cercli/*/
        if test -d "$d/.git"
            echo $d
        end
    end
end

# Disable file completion by default
complete -c nova -f

# Top-level subcommands
complete -c nova -n '__fish_use_subcommand' -a start -d 'Start a Claude Code session in tmux'
complete -c nova -n '__fish_use_subcommand' -a list -d 'List active sessions'
complete -c nova -n '__fish_use_subcommand' -a ls -d 'List active sessions (alias)'
complete -c nova -n '__fish_use_subcommand' -a attach -d 'Attach to a session'
complete -c nova -n '__fish_use_subcommand' -a peek -d 'View session output without attaching'
complete -c nova -n '__fish_use_subcommand' -a kill -d 'Kill a session'
complete -c nova -n '__fish_use_subcommand' -a windows -d 'List raw tmux windows'
complete -c nova -n '__fish_use_subcommand' -a rotate -d 'Rotate (recycle) a session'
complete -c nova -n '__fish_use_subcommand' -a dream -d 'Run dream agent (interactive)'
complete -c nova -n '__fish_use_subcommand' -a meditate -d 'Run meditate agent (interactive)'
complete -c nova -n '__fish_use_subcommand' -a exchange -d 'Manage the exchange daemon'

# --- start ---
complete -c nova -n '__fish_seen_subcommand_from start' -a '(__nova_repos)' -d 'Repository path'
complete -c nova -n '__fish_seen_subcommand_from start' -s n -l name -d 'Session name' -r
complete -c nova -n '__fish_seen_subcommand_from start' -s a -l agent -d 'Agent config name' -r -a '(__nova_agents)'
complete -c nova -n '__fish_seen_subcommand_from start' -s r -l resume -d 'Resume session by ID' -r
complete -c nova -n '__fish_seen_subcommand_from start' -s p -l permission-mode -d 'Permission mode' -r -a 'acceptEdits default plan bypassPermissions'

# --- attach ---
complete -c nova -n '__fish_seen_subcommand_from attach' -a '(__nova_sessions)' -d 'Session name'

# --- peek ---
complete -c nova -n '__fish_seen_subcommand_from peek' -a '(__nova_sessions)' -d 'Session name'
complete -c nova -n '__fish_seen_subcommand_from peek' -s l -l lines -d 'Number of lines (default: 50)' -r

# --- kill ---
complete -c nova -n '__fish_seen_subcommand_from kill' -a '(__nova_sessions)' -d 'Session name'

# --- rotate ---
complete -c nova -n '__fish_seen_subcommand_from rotate' -a '(__nova_slack_sessions)' -d 'Session name'

# --- exchange subcommands ---
complete -c nova -n '__fish_seen_subcommand_from exchange; and not __fish_seen_subcommand_from start install' -a start -d 'Start exchange daemon (foreground)'
complete -c nova -n '__fish_seen_subcommand_from exchange; and not __fish_seen_subcommand_from start install' -a install -d 'Install as launchd service'
