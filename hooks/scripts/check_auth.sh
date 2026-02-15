#!/bin/bash
# CodeAlive API key check — runs on Claude Code session start.
# If the key is missing, injects a warning into Claude's context.

KEY="${CODEALIVE_API_KEY:-}"

# Try macOS Keychain
if [ -z "$KEY" ] && command -v security &>/dev/null; then
  KEY=$(security find-generic-password -a "$USER" -s "codealive-api-key" -w 2>/dev/null || true)
fi

# Try Linux secret-tool
if [ -z "$KEY" ] && command -v secret-tool &>/dev/null; then
  KEY=$(secret-tool lookup service codealive-api-key 2>/dev/null || true)
fi

if [ -z "$KEY" ]; then
  # Find setup.py relative to plugin root
  PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(dirname "$(dirname "$0")")}"
  SETUP_PATH="${PLUGIN_ROOT}/skills/codealive-context-engine/setup.py"

  cat <<EOF
{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"[CodeAlive] API key is not configured. The codealive-context-engine skill requires authentication.\n\nOption 1 (recommended): run interactive setup: python ${SETUP_PATH}\nOption 2 (not recommended — key visible in chat history): ask the user to paste their key, then run: python ${SETUP_PATH} --key THE_KEY\nGet key at: https://app.codealive.ai/settings/api-keys"}}
EOF
fi

exit 0
