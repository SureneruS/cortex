#!/bin/bash
set -euo pipefail

PHASE="${1:---phase1}"

if [ "$PHASE" != "--phase1" ]; then
  echo "error: only --phase1 is supported (phase 2 deferred until verified)"
  exit 1
fi

echo "=== Memory Migration Phase 1 (reversible, all copies) ==="

WORKSPACE_MEMORY="$HOME/.claude/projects/-Users-suren-workspace-cercli/memory"
ARCHIVE_DIR="$HOME/.claude/projects/-Users-suren-workspace-cercli/memory.archive"
RULES_DIR="$HOME/.claude/rules"
CLAUDE_MD="$HOME/.claude/CLAUDE.md"

# --- 1. Archive workspace memory ---
if [ -d "$WORKSPACE_MEMORY" ]; then
  if [ -d "$ARCHIVE_DIR" ]; then
    echo "  skip: memory.archive/ already exists"
  else
    cp -R "$WORKSPACE_MEMORY" "$ARCHIVE_DIR"
    echo "  copied: memory/ -> memory.archive/"
  fi
else
  echo "  skip: no workspace memory directory found"
fi

# --- 2. Copy feedback files to global rules ---
mkdir -p "$RULES_DIR"
feedback_count=0

for f in "$WORKSPACE_MEMORY"/feedback_*.md; do
  [ -f "$f" ] || continue
  dest="$RULES_DIR/$(basename "$f")"
  if [ -f "$dest" ]; then
    echo "  skip: $(basename "$f") already in rules/"
  else
    cp "$f" "$dest"
    feedback_count=$((feedback_count + 1))
  fi
done

echo "  copied $feedback_count feedback files to ~/.claude/rules/"

# --- 3. Create python-patterns.md from CLAUDE.md sections ---
PATTERNS_FILE="$RULES_DIR/python-patterns.md"

if [ -f "$PATTERNS_FILE" ]; then
  echo "  skip: python-patterns.md already exists"
else
  # Extract sections between "## Architecture Principles" and "## PR Workflow"
  sed -n '/^## Architecture Principles$/,/^## PR Workflow$/p' "$CLAUDE_MD" | sed '$ d' > "$PATTERNS_FILE"
  echo "  created: ~/.claude/rules/python-patterns.md"
fi

echo ""
echo "=== Phase 1 complete ==="
echo "Originals untouched. To revert:"
echo "  rm -rf $ARCHIVE_DIR"
echo "  rm $RULES_DIR/feedback_*.md"
echo "  rm $RULES_DIR/python-patterns.md"
