#!/usr/bin/env bash
# Inject cortex rules as additionalContext on SessionStart
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
PLUGIN_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

RULES_FILE="${PLUGIN_ROOT}/.claude/rules/cortex-rules.md"

if [ ! -f "$RULES_FILE" ]; then
    echo '{}'
    exit 0
fi

rules_content=$(cat "$RULES_FILE")

escape_for_json() {
    local s="$1"
    s="${s//\\/\\\\}"
    s="${s//\"/\\\"}"
    s="${s//$'\n'/\\n}"
    s="${s//$'\r'/\\r}"
    s="${s//$'\t'/\\t}"
    printf '%s' "$s"
}

escaped=$(escape_for_json "$rules_content")

cat <<EOF
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "${escaped}"
  }
}
EOF
