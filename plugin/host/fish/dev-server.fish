function dev-server -d "Manage local dev servers in tmux"
    set -l base /Users/suren/workspace/cercli
    set -l session dev-server

    if test (count $argv) -eq 0
        set argv[1] help
    end

    switch $argv[1]
        case start
            if tmux has-session -t $session 2>/dev/null
                echo "dev-server already running"
                dev-server status
                return 0
            end

            # cercli-backend
            tmux new-session -d -s $session -n cercli-backend -c "$base/cercli-backend"
            tmux send-keys -t $session:cercli-backend \
                "git checkout main && git pull && poetry install && poetry run python manage.py runserver_ui" Enter

            # recruitment-backend
            tmux new-window -t $session -n recruitment-backend -c "$base/recruitment-backend"
            tmux send-keys -t $session:recruitment-backend \
                "git checkout main && git pull && uv sync && docker compose -f docker-compose.dev.yml up --build" Enter

            # frontend
            tmux new-window -t $session -n frontend -c "$base/frontend"
            tmux send-keys -t $session:frontend \
                "git checkout main && git pull && pnpm install && pnpm dev --filter app" Enter

            echo "dev-server started"
            echo "  cercli-backend   → https://portal.localhost:8000"
            echo "  recruitment-backend → http://localhost:8080"
            echo "  frontend           → http://localhost:3000"
            echo ""
            echo "Attach: tmux attach -t dev-server"

        case stop
            if not tmux has-session -t $session 2>/dev/null
                echo "dev-server is not running"
                return 1
            end

            # Ctrl+C all windows
            for win in cercli-backend recruitment-backend frontend
                tmux send-keys -t $session:$win C-c 2>/dev/null
            end
            sleep 3

            # docker compose down for recruitment-backend
            tmux send-keys -t $session:recruitment-backend \
                "docker compose -f docker-compose.dev.yml down" Enter
            sleep 5

            tmux kill-session -t $session
            echo "dev-server stopped"

        case status
            if not tmux has-session -t $session 2>/dev/null
                echo "dev-server is not running"
                return 1
            end

            echo "dev-server running:"
            for win in cercli-backend recruitment-backend frontend
                set -l pane_path (tmux display-message -t $session:$win -p '#{pane_current_path}' 2>/dev/null)
                if test -n "$pane_path"
                    echo "  $win → $pane_path"
                end
            end

        case switch
            if test (count $argv) -lt 3
                echo "Usage: dev-server switch <service> <main|branch-name|/path>"
                echo ""
                echo "Services: cercli-backend, recruitment-backend, frontend"
                echo ""
                echo "Examples:"
                echo "  dev-server switch recruitment-backend main"
                echo "  dev-server switch recruitment-backend feat/ATS-123-my-feature"
                echo "  dev-server switch recruitment-backend /full/path/to/worktree"
                return 1
            end

            set -l service $argv[2]
            set -l target $argv[3]

            if not tmux has-session -t $session 2>/dev/null
                echo "dev-server is not running. Run: dev-server start"
                return 1
            end

            # Resolve target directory
            set -l target_dir
            if test -d "$target"
                set target_dir $target
            else if test "$target" = main
                set target_dir "$base/$service"
            else
                # Look for worktree
                set -l wt_dir "$base/$service/.worktrees/$target"
                if test -d "$wt_dir"
                    set target_dir $wt_dir
                else
                    echo "No worktree found at $wt_dir"
                    echo "Create one first, or pass a full path"
                    return 1
                end
            end

            # Stop current server
            tmux send-keys -t $session:$service C-c
            sleep 2

            # Extra cleanup for recruitment-backend (docker)
            if test "$service" = recruitment-backend
                tmux send-keys -t $session:$service \
                    "docker compose -f docker-compose.dev.yml down" Enter
                sleep 5
            end

            # Start from new directory
            switch $service
                case cercli-backend
                    tmux send-keys -t $session:$service \
                        "cd $target_dir && poetry install && poetry run python manage.py runserver_ui" Enter
                case recruitment-backend
                    tmux send-keys -t $session:$service \
                        "cd $target_dir && uv sync && docker compose -f docker-compose.dev.yml up --build" Enter
                case frontend
                    tmux send-keys -t $session:$service \
                        "cd $target_dir && pnpm install && pnpm dev --filter app" Enter
                case '*'
                    echo "Unknown service: $service"
                    return 1
            end

            echo "Switched $service → $target_dir"

        case logs
            if test (count $argv) -lt 2
                echo "Usage: dev-server logs <cercli-backend|recruitment-backend|frontend>"
                return 1
            end

            if not tmux has-session -t $session 2>/dev/null
                echo "dev-server is not running"
                return 1
            end

            tmux attach -t $session:$argv[2]

        case help '*'
            echo "Usage: dev-server <command>"
            echo ""
            echo "Commands:"
            echo "  start                              Pull latest main, install deps, start all servers"
            echo "  stop                               Stop all servers and kill tmux session"
            echo "  status                             Show running servers and their directories"
            echo "  switch <service> <main|branch|path> Switch a service to a different branch/worktree"
            echo "  logs <service>                     Attach to a service's tmux window"
    end
end
