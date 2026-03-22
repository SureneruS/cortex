#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Cortex Slice 1 Setup ==="
echo ""

# --- 1. Per-repo plans directories ---
echo "--- Step 1: Per-repo plansDirectory ---"
"$SCRIPT_DIR/setup-repo-plans.sh"
echo ""

# --- 2. Memory migration (phase 1 only) ---
echo "--- Step 2: Memory migration (phase 1) ---"
"$SCRIPT_DIR/migrate-memory.sh" --phase1
echo ""

# --- 3. Print required settings.json changes ---
echo "--- Step 3: Manual settings.json changes needed ---"
echo ""
echo "Add the following to ~/.claude/settings.json (merge manually):"
echo ""
cat <<'SETTINGS'
{
  "cleanupPeriodDays": 3650,
  "additionalDirectories": [
    "~/workspace/cercli/arc",
    "~/workspace/cercli/cercli-backend",
    "~/workspace/cercli/cortex",
    "~/workspace/cercli/frontend",
    "~/workspace/cercli/infrastructure",
    "~/workspace/cercli/orbit",
    "~/workspace/cercli/recruitment-backend",
    "~/workspace/cercli/storage-service",
    "~/workspace/cercli/suren-claude-docs",
    "~/workspace/cercli/suren-toolbox",
    "~/workspace/cercli/workflows-backend"
  ],
  "enableAllProjectMcpServers": true,
  "worktree": {
    "symlinkDirectories": [".venv", "node_modules"]
  },
  "hooks": {
    "Notification": [
      {
        "matcher": "permission_prompt|idle_prompt",
        "hooks": [
          {
            "type": "command",
            "command": "osascript -e 'display notification \"Claude Code needs your attention\" with title \"Claude Code\"'"
          }
        ]
      }
    ],
    "SessionEnd": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "jq -r '.session_id // empty' | xargs -I{} cortex session close {} 2>/dev/null; osascript -e 'display notification \"Session finished\" with title \"Claude Code\"'"
          }
        ]
      }
    ]
  }
}
SETTINGS
echo ""

# --- 4. Smoke test (if available) ---
if command -v cortex &>/dev/null; then
  echo "--- Step 4: Smoke test ---"
  cortex test smoke slice-1 2>/dev/null || echo "  (cortex test smoke not yet available — skip)"
else
  echo "--- Step 4: Smoke test ---"
  echo "  cortex CLI not on PATH — skip smoke test"
fi

echo ""
echo "=== Setup complete ==="
echo "Next: manually merge settings.json changes above, then verify with a test session."
