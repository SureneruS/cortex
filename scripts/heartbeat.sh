#!/usr/bin/env bash
# Outputs a metric-row JSON array with live timestamp and PR count
TIMESTAMP=$(date +%H:%M:%S)
PR_COUNT=$(gh pr list --repo cercli/recruitment-backend --state open --author @me --json number 2>/dev/null | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "?")

cat <<EOF
[
  {"label": "Last Refresh", "value": "$TIMESTAMP", "color": "green"},
  {"label": "Open PRs", "value": $PR_COUNT, "color": "blue"},
  {"label": "PID", "value": $$, "color": "muted"}
]
EOF
