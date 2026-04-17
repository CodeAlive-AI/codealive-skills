#!/usr/bin/env bash
# Point an agent-side symlink at the highest-versioned cache directory of an
# installed Claude Code plugin. Safe to re-run; relinks only when the target
# changes.
#
# Configuration (override via environment):
#   CODEALIVE_PLUGIN_CACHE     Parent of versioned plugin directories
#                              Default: ~/.claude/plugins/cache/codealive-marketplace/codealive
#   CODEALIVE_PLUGIN_SUBPATH   Skill path inside each versioned directory
#                              Default: skills/codealive-context-engine
#   CODEALIVE_AGENT_LINK       Symlink to create or update
#                              Default: ~/.codex/skills/codealive-context-engine

set -u

: "${CODEALIVE_PLUGIN_CACHE:=$HOME/.claude/plugins/cache/codealive-marketplace/codealive}"
: "${CODEALIVE_PLUGIN_SUBPATH:=skills/codealive-context-engine}"
: "${CODEALIVE_AGENT_LINK:=$HOME/.codex/skills/codealive-context-engine}"

[ -d "$CODEALIVE_PLUGIN_CACHE" ] || exit 0

LATEST=$(ls -1 "$CODEALIVE_PLUGIN_CACHE" 2>/dev/null | sort -V | tail -1)
[ -n "$LATEST" ] || exit 0

TARGET="$CODEALIVE_PLUGIN_CACHE/$LATEST/$CODEALIVE_PLUGIN_SUBPATH"
[ -d "$TARGET" ] || exit 0

mkdir -p "$(dirname "$CODEALIVE_AGENT_LINK")"

CURRENT=$(readlink "$CODEALIVE_AGENT_LINK" 2>/dev/null || true)
if [ "$CURRENT" != "$TARGET" ]; then
  ln -sfn "$TARGET" "$CODEALIVE_AGENT_LINK"
  echo "$(date -u +%FT%TZ) linked $CODEALIVE_AGENT_LINK -> $TARGET"
fi
