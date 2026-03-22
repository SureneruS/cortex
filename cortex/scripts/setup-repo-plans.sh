#!/bin/bash
set -euo pipefail

WORKSPACE="$HOME/workspace/cercli"
DOCS_DIR="$WORKSPACE/suren-claude-docs"

echo "Setting up per-repo plansDirectory..."

for repo_dir in "$WORKSPACE"/*/; do
  [ -d "$repo_dir/.git" ] || continue

  repo_name=$(basename "$repo_dir")

  # Skip suren-claude-docs itself
  [ "$repo_name" = "suren-claude-docs" ] && continue

  plans_dir="$DOCS_DIR/$repo_name/plans"
  mkdir -p "$plans_dir"

  settings_file="$repo_dir/.claude/settings.local.json"
  plans_value="$HOME/workspace/cercli/suren-claude-docs/$repo_name/plans"

  if [ -f "$settings_file" ]; then
    # Merge plansDirectory into existing settings
    tmp=$(mktemp)
    jq --arg pd "$plans_value" '.plansDirectory = $pd' "$settings_file" > "$tmp"
    mv "$tmp" "$settings_file"
    echo "  updated: $repo_name/.claude/settings.local.json"
  else
    mkdir -p "$repo_dir/.claude"
    printf '{\n  "plansDirectory": "%s"\n}\n' "$plans_value" > "$settings_file"
    echo "  created: $repo_name/.claude/settings.local.json"
  fi
done

echo "Done. Plans directories created in suren-claude-docs/."
