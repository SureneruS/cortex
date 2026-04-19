#!/bin/sh
# Cortex desktop notification hook — posts a native macOS notification
# via terminal-notifier when CC emits a permission_prompt or idle_prompt.
# Shown subtitle is the Cortex session name (falls back to "Session").

input=$(cat)
msg=$(echo "$input" | jq -r .message)
name=""
if [ -n "$CORTEX_SESSION_ID" ]; then
  name=$(cortex session get "$CORTEX_SESSION_ID" 2>/dev/null | jq -r .name 2>/dev/null)
fi
terminal-notifier \
  -title Cortex \
  -subtitle "${name:-Session}" \
  -message "$msg" \
  -group cortex-notification
